"""Secret-free requirements and deterministic infrastructure planning for agents.

The agent interprets the conversation. This module validates its explicit record;
it does not infer consent, use cases or protocol readiness from prose.
"""

from urllib.parse import urlsplit

DECISIONS = (
    "install_spx_ui",
    "start",
    "service_bind_addresses",
    "port_mappings",
    "replace_existing",
)
SCOPES = ["selected", "full_catalog", "base"]
SCHEMA = {
    "description": "User's intended application (no credentials)",
    "catalog_scope": SCOPES,
    "protocols": "Protocols actually needed now; registered models alone do not enable protocols",
    "required_services": "Additional required service IDs",
    "external_services": "Service ID -> {endpoint: credential-free URL with explicit port, provisioning: runtime configuration instructions}",
    "remove_services": "Existing service IDs explicitly agreed to be removed",
    "unresolved": "Unanswered questions; a nonempty list blocks planning",
    "decisions": "Reviewed values of: " + ", ".join(DECISIONS),
}


def validate_requirements(value, index):
    """Reject malformed/secret-bearing fields; incomplete drafts remain editable."""
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - set(SCHEMA):
        raise ValueError("Invalid requirements fields; use requirements_schema")
    if "description" in value and (
        not isinstance(value["description"], str) or len(value["description"]) > 8192
    ):
        raise ValueError("requirements.description must be a short, secret-free string")
    if "catalog_scope" in value and value["catalog_scope"] not in SCOPES:
        raise ValueError("Choose selected, full_catalog or base catalog scope")
    protocols = {p for m in index.models.values() for p in m.protocols} | {
        s.protocol for s in index.services.values()
    }
    for field, available in (
        ("protocols", protocols),
        ("required_services", index.services),
        ("remove_services", index.services),
    ):
        entries = value.get(field, [])
        if not isinstance(entries, list) or any(
            not isinstance(x, str) or x not in available for x in entries
        ):
            raise ValueError("Invalid requirements." + field)
    unresolved = value.get("unresolved", [])
    if not isinstance(unresolved, list) or any(
        not isinstance(x, str) for x in unresolved
    ):
        raise ValueError("requirements.unresolved must be a list of questions")
    decisions = value.get("decisions", {})
    if not isinstance(decisions, dict) or set(decisions) - set(DECISIONS):
        raise ValueError("Invalid requirements.decisions")
    for field in DECISIONS:
        if field not in decisions:
            continue
        expected = (
            dict if field in {"service_bind_addresses", "port_mappings"} else bool
        )
        if type(decisions[field]) is not expected:
            raise ValueError("Invalid requirements decision: " + field)
    external = value.get("external_services", {})
    if not isinstance(external, dict):
        raise ValueError("external_services must be a mapping")
    schemes = {
        "mqtt": {"mqtt", "mqtts"},
        "knx": {"knx", "udp", "tcp"},
        "lwm2m": {"coap", "coaps"},
        "http": {"http", "https"},
        "matter": {"ws", "wss", "http", "https"},
    }
    for sid, definition in external.items():
        service = index.services.get(sid)
        if (
            not service
            or not service.deployment
            or service.deployment.runtime != "docker"
        ):
            raise ValueError(
                "Only separately deployed services can be declared external"
            )
        if not isinstance(definition, dict) or set(definition) != {
            "endpoint",
            "provisioning",
        }:
            raise ValueError(
                "External service needs endpoint and provisioning instructions"
            )
        if any(
            not isinstance(v, str) or not v.strip() or len(v) > 2048
            for v in definition.values()
        ):
            raise ValueError("External service fields must be short, nonempty strings")
        endpoint = definition["endpoint"]
        try:
            url = urlsplit(endpoint)
            port = url.port
        except ValueError as exc:
            raise ValueError(
                "Invalid external endpoint; do not include credentials"
            ) from exc
        if (
            url.scheme not in schemes.get(service.protocol, set())
            or not url.hostname
            or port is None
            or not 1 <= port <= 65535
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(c.isspace() for c in endpoint)
        ):
            raise ValueError(
                "External endpoint must use the service transport, an explicit port and no credentials"
            )


def service_closure(seeds, index, external=()):
    """An external provider owns its dependencies; local ones need Compose peers."""
    result, visiting = set(), set()
    external = set(external)

    def add(sid):
        if sid in external or sid in result:
            return
        if sid in visiting:
            raise ValueError("Cyclic service dependencies")
        if sid not in index.services:
            raise ValueError("Unknown service dependency")
        visiting.add(sid)
        deployment = index.services[sid].deployment
        if deployment:
            for dependency in deployment.depends_on:
                add(dependency)
        visiting.remove(sid)
        result.add(sid)

    for sid in seeds:
        add(sid)
    return sorted(result)


def required_services(requirements, model_ids, index):
    if not requirements:
        return []
    protocols = set(requirements.get("protocols", []))
    scope = requirements.get("catalog_scope")
    seeds = set(requirements.get("required_services", []))
    for mid in model_ids:
        model = index.models[mid]
        # Full catalogs are libraries. Infrastructure is provisioned only for
        # requested protocols, rather than every registered model's transport.
        if scope == "full_catalog" and not protocols.intersection(model.protocols):
            continue
        seeds.update(model.services)
    return service_closure(seeds, index, requirements.get("external_services", {}))


def assess_requirements(value, selection, index, installed):
    """Return actionable blockers; never silently drop requirements or services."""
    req = value.get("requirements")
    errors = []

    def error(code, message, **details):
        errors.append({"code": code, "message": message, **details})

    if (
        not req
        or not req.get("description", "").strip()
        or not req.get("catalog_scope")
    ):
        error(
            "REQUIREMENTS_INCOMPLETE",
            "Ask what the user wants to use SPX for and record the intended catalog scope.",
        )
        return errors
    for field in (
        "protocols",
        "required_services",
        "external_services",
        "remove_services",
        "unresolved",
        "decisions",
    ):
        if field not in req:
            error(
                "REQUIREMENTS_INCOMPLETE",
                "Record the setup decision: " + field,
                field=field,
            )
    for field in DECISIONS:
        if (
            field not in req.get("decisions", {})
            or req["decisions"][field] != value[field]
        ):
            error(
                "SETUP_DECISION_REQUIRED",
                "Review the current value of "
                + field
                + " with the user (accepted proposed defaults are allowed).",
                field=field,
            )
    if req.get("unresolved"):
        error(
            "REQUIREMENTS_INCOMPLETE",
            "Resolve the remaining questions before proposing installation.",
            questions=req["unresolved"],
        )
    model_ids = selection.model_ids
    if req["catalog_scope"] == "base" and model_ids:
        error(
            "CATALOG_SCOPE_MISMATCH",
            "Base-only installation must not include catalog models.",
        )
    if req["catalog_scope"] == "selected" and not model_ids:
        error(
            "CATALOG_SCOPE_MISMATCH",
            "Select models for the described use case, or explicitly choose base-only installation.",
        )
    from .selection import apply_platform_compatibility

    available_models = apply_platform_compatibility(
        model_ids=list(index.models),
        service_ids=selection.service_ids,
        instances=[],
        start_instances=[],
        index=index,
    ).model_ids
    if req["catalog_scope"] == "selected" and (
        set(model_ids) == set(available_models)
        or (index.industries and set(value["packages"]) == set(index.industries))
    ):
        error(
            "CATALOG_SCOPE_MISMATCH",
            "The full catalog requires explicit full_catalog scope.",
        )
    if req["catalog_scope"] == "full_catalog" and set(model_ids) != set(
        available_models
    ):
        error(
            "CATALOG_SCOPE_MISMATCH",
            "Full catalog scope must include all supported models on this platform.",
        )
    for protocol in req.get("protocols", []):
        if not any(protocol in index.models[mid].protocols for mid in model_ids):
            error(
                "MISSING_REQUIRED_PROTOCOL",
                "Select a supported model for the required protocol.",
                protocol=protocol,
            )
    external = req.get("external_services", {})
    for sid in external:
        if sid in selection.service_ids:
            error(
                "AMBIGUOUS_SERVICE_PROVIDER",
                "Choose either a local or external provider.",
                service_id=sid,
            )
    needed = required_services(req, model_ids, index)
    # Explicitly selected local services also require their transitive peers.
    needed = service_closure(set(needed) | set(selection.service_ids), index, external)
    for sid in sorted(set(needed) - set(selection.service_ids)):
        error(
            "MISSING_REQUIRED_SERVICE",
            "Include the required local service or explicitly configure its external provider.",
            service_id=sid,
        )
    removed = set(installed.get("service_ids", [])) - set(selection.service_ids)
    for sid in sorted(removed - set(req.get("remove_services", []))):
        error(
            "SERVICE_REMOVAL_UNCONFIRMED",
            "Confirm removal of the installed service, including replacement by an external provider.",
            service_id=sid,
        )
    return errors


def external_summary(requirements):
    return {
        sid: {**v, "verified": False}
        for sid, v in (requirements or {}).get("external_services", {}).items()
    }
