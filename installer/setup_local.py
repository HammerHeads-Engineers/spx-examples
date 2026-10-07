"""Use Setup's staging/journal for existing wizard and direct generation flows."""

from dataclasses import asdict

from .setup_session import SetupEngine


def execute_selection(
    selection,
    output,
    *,
    catalog=None,
    profiles=None,
    start_callback=None,
    workspace=None,
    prepare_mcp_before_install=False,
):
    resolved = asdict(selection)
    resolved.pop("license_key")
    install_models = resolved.pop("install_examples")
    resolved.pop("offline_bundle")
    resolved.update(
        install_models=install_models,
        install_instances=bool(selection.instances),
        start=False,
    )
    # Local rendering retains its established Docker/replacement prompts; the
    # agent adapter instead preflights and approves everything before its job.
    engine = SetupEngine()
    session = engine.create(
        output,
        selection.license_key,
        initial=resolved,
        catalog=catalog,
        profiles=profiles,
        validate_key=False,
    )
    if workspace is not None:
        private = engine._read(session["session_id"])
        private["workspace"] = str(workspace)
        engine._write(private)
    if prepare_mcp_before_install:
        from .setup_workspace import default_workspace, prepare_workspace

        try:
            prepare_workspace(
                workspace or default_workspace(),
                engine,
                session["session_id"],
                preserve_session=True,
            )
        except Exception:
            # The ordinary wizard can still install the stack. Tool repair is
            # reported independently after deployment by prepare_tools.
            print(
                "[spx-installer] MCP preparation failed; installation will continue and retry tool setup after deployment."
            )
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"], start_callback=start_callback)
    result = engine.get(session["session_id"])
    return result
