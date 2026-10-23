# Wyniki remediacji eMudhra / emSign — 6424

Stan walidacji: 2026-10-23. Zmiany przygotowano do PR-ów z bazą `develop`
na gałęziach `fix/emsign-bootstrap`. Poniższe wyniki pochodzą z lokalnej walidacji
przed wysłaniem PR-ów. Nie opublikowano wydania ani nie wdrożono produkcji.
Pierwotny checkout spx-examples z lokalnymi zmianami użytkownika pozostawiono bez zmian.

## Uzupełnienie po review i publikacji RC74

- Server #76 i poprawka uwierzytelniania wydania #77 są zmergowane do `develop`.
  Opublikowano `v1.0.0-rc.74` dla linux/amd64 i linux/arm64; digest indeksu:
  `sha256:9003cdcf2e88465238c815ad9278971ad5b6a184a2b47104bf076ec2f88989a5`.
- Natywne testy instalatora Windows 2022/2025, macOS ARM64/Intel oraz Linux
  przeszły po poprawieniu wykrywania Pythona 3.13 i rozdzieleniu interpretera
  budującego od instalowanego runtime na Windows.
- Obraz Matter nadal nie przeszedł kwalifikacji magazynu CA. Nie naprawiono
  zewnętrznych obrazów Home Assistant/Matter ani nie uznano zadania 6424 za zamknięte.
- Obowiązkowa kwalifikacja instalatora sprawdza wszystkie obrazy Pythona
  obecne w wygenerowanym Compose, przed uruchomieniem stosu. Przemysłowy starter
  nie zawiera Home Assistanta ani Matter. Jeśli wybrany stos je zawiera, podlegają
  temu samemu blokującemu testowi bezpieczeństwa.
- Pełny audyt katalogu pozostaje dostępny w ręcznym workflow
  `Catalog Python image security audit` i przez `python -m tools.verify_python_images`.
  Poniższe wyniki i blokady opisują wcześniejszy etap lokalnej walidacji.

## Zakres i źródła

- spx-examples: worktree na bazie develop `4d9a8f8` (RC108).
- spx-server: sklonowane prywatne repozytorium HammerHeads-Engineers/spx-server,
  baza develop `c20da3d` (RC73).
- [Instrukcja migracji i opis komponentów](EMSIGN_6424.md).
- Oficjalne advisory i wydanie CPython 3.13.17 przeczytano przed zmianą pinów.
- Strona zadania Azure 6424 była niedostępna przez narzędzie WWW. Nie zamieszczano komentarza w zadaniu.

## Zweryfikowane wyniki

| Kontrola | Wynik |
|---|---|
| Zmienione ścieżki instalatora, MCP, CI, pakietów i regresje | **108 PASS**, 1 test macOS notarization pominięty w tej komendzie z powodu lokalnego Bash/Windows |
| Regresje bezpieczeństwa w spx-server | **8 PASS** |
| `tools/validate_models.py` | **PASS** |
| `poetry check --lock`, YAML workflowów, lint zmienionych plików, `git diff --check` | **PASS** |
| spx-server: `flake8 .` | **PASS** |
| Czysty venv i instalacja pakietu | **PASS**, pip 26.2.2, certifi 2026.10.23 |
| Upgrade venv: pip 25.0.1 / certifi 2025.8.3, zgodny znacznik | **PASS**, pip 26.2.2, certifi 2026.10.23; znacznik zachowany |
| Ponowne użycie naprawionego runtime | **PASS** |
| Ponowny `poetry sync` na Pythonie 3.12.10 | **PASS**, certifi 2026.10.23; zachowane NumPy 2.0.2 / SciPy 1.13.1 |
| Instalacja i ponowny `poetry sync` na Pythonie 3.13.17 | **PASS**, pip 26.2.2, certifi 2026.10.23, NumPy 2.1.3 / SciPy 1.14.1 |
| Bootstrap narzędzi CI w osobnym venv | **PASS**, Poetry 2.2.1; synchronizacja aplikacji nie usuwa narzędzi CI |
| Kontrola TLS, PIP_CERT, REQUESTS_CA_BUNDLE, HTTPS_PROXY | **PASS**; weryfikacja TLS zachowana, ustawienia dziedziczone |
| Archiwum `.tgz` i samorozpakowujące `.run` / `.ps1` | **ZBUDOWANE lokalnie**, wersja QA `0.0.0-emsign-qa` |
| Linux portable: pierwszy start CLI i ponowne użycie runtime | **PASS**, pip 26.2.2, certifi 2026.10.23, Python 3.13.17 |
| SHA-256 bootstrapu w faktycznej zawartości archiwum | **PASS** |
| Obraz SPX Server linux/amd64, `--pull --no-cache` | **ZBUDOWANY i zweryfikowany**, oba interpretery: Python 3.13.17, pip 26.2.2, certifi 2026.10.23 |
| Obraz: ensurepip / certifi wewnątrz pip | 26.2.2 / 2026.10.19 |
| Obraz: systemowy magazyn CA i domyślna kontrola TLS | **PASS**, ca-certificates 20250419+deb13u1, brak emSign ECC Root CA - G3 w domyślnym magazynie |
| Start CLI skompilowanego serwera w gotowym obrazie | **PASS**, `--help` |

Lokalny obraz: `spx-server:emsign-qa`, ID
`sha256:cbef568e4449629ed2c182b34e0bbb7ea169c4e669e49cceb6e5218a6405f8d0`.
Nie jest opublikowanym wydaniem ani potwierdzeniem całego wdrożenia.

Dawne wersje pip/certifi użyte w teście regresji pobrano poprawionym pip,
a następnie zainstalowano offline. Stary pip nie wykonywał instalacji z indeksu.
UV 0.13.5 wykorzystano wyłącznie jako lokalne narzędzie QA do uzyskania
interpretera 3.13.17; nie dodano pip/uv/Poetry do zależności aplikacji.

## Szersze testy i ograniczenia

- spx-server: **1031 PASS, 2 FAIL, 25 SKIP**. Oba błędy odtworzono na
  niezmienionej bazie develop: automatyczny wybór portu SCPI i tymczasowe
  odłączanie scenariusza Modbus. Nie naprawiano ich w tej zmianie bezpieczeństwa.
- spx-examples: szersza komenda dla installer / MCP unit / core unit:
  **694 PASS, 6 FAIL, 24 SKIP, 6 deselected**. Cztery błędy dotyczą użycia
  windowsowego launchera Bash do skryptów POSIX (pakowanie / cleanup).
  Jeden błąd Setup (`test_new_revision_after_success_can_apply_and_clears_old_diagnostics`)
  odtworzono także na niezmienionej bazie. Test zachowania snapshotu przeszedł
  przy oddzielnym powtórzeniu na bazie i na zmianie. Nie deklaruje się pełnego zielonego pytest.
- Nowe testy regresji bezpieczeństwa i ostatni zestaw 108 testów są zielone.
- Nie wykonano pełnego uruchomienia gotowego serwera z licencją testową ani
  kwalifikacji ARM64. Sprawdzono wersje, TLS, CA i start CLI obrazu AMD64.
- Natywny MSI/EXE nie został zbudowany: lokalnie brak SDK .NET i WiX.
  Natywnego PKG nie można zbudować na tym hoście Windows. Potrzebne są
  odpowiednie runnery, podpisy, testy nowej i istniejącej instalacji oraz MCP.
- Oficjalne payloady natywnego Pythona są przypięte do 3.13.17 i SHA-256
  ze strony python.org. Nie utożsamia się tego z testem gotowego instalatora SPX.

## Blokady wydania

1. Opublikować dopiero po osobnym poleceniu zweryfikowany obraz SPX Server,
   następnie zmienić piny compose / compatibility w spx-examples na jego tag/digest.
   Obecne piny RC nie są zastępowane wymyślonym przyszłym numerem wydania.
2. Opcjonalny lokalny Home Assistant nadal ma **pip 26.0.1, uv 0.12.23,
   certifi 2026.7.22**. Kontrola gotowego obrazu odrzuca go również ze względu
   na stary systemowy magazyn z emSign G3. Nie zmieniano działającego kontenera.
   Należy uzyskać i zweryfikować poprawiony obraz oraz odtworzyć usługę z zachowaniem danych.
3. Oddzielnie zakwalifikować aktualny obraz python-matter-server.
   Oba zewnętrzne obrazy są objęte nową kontrolą wydania z katalogu usług.
4. Przeprowadzić natywne testy Windows/macOS, aktualizacje istniejących instalacji,
   ARM64 i test zdrowia serwera z licencją. Kontrola obrazu w CI sprawdza jego
   pierwotny stan, zanim testy zainstalują pakiety lub naprawią pip.
5. Pełna kwalifikacja wydania musi uwzględnić opisane błędy szerszych testów.

## Gotowa treść do zadania 6424

Przygotowano lokalne poprawki źródłowe w spx-examples i spx-server:
wersjonowany, SHA-256-pinned bootstrap pip przed innymi instalacjami,
bezwarunkową kontrolę bezpieczeństwa przy ponownym użyciu venv i zgodnym
znaczniku, certifi >=2026.10.19 (lock 2026.10.23), ochronę ścieżek instalatora,
workspace/MCP i generowanego runtime, zabezpieczenie CI oraz obu etapów obrazu.
Natywne runtime'y przełączono na Python 3.13.17 z poprawionym ensurepip.
Dodano kontrolę gotowych obrazów z katalogu usług przed naprawą środowiska testowego.

Zaliczone: 108 testów wybranych ścieżek i regresji, 8 regresji serwera,
walidacja modeli, lint i lockfile, rzeczywista czysta instalacja/upgrade
podatnego venv przy zgodnym znaczniku, ponowna synchronizacja na Pythonie
3.12 i 3.13, budowa archiwów portable i uruchomienie ich CLI, budowa bez cache
oraz kontrola obu interpreterów obrazu AMD64 (pip 26.2.2, certifi 2026.10.23).
TLS pozostał włączony; ustawień proxy/certyfikatów nie zmieniano.

Zadanie pozostaje otwarte: wymagane są natywne artefakty i testy aktualizacji,
ARM64, opublikowany i przypięty poprawiony obraz serwera, kwalifikacja obrazów
zewnętrznych oraz rozstrzygnięcie błędów szerszych testów. W lokalnym Home Assistant
potwierdzono nadal podatne pip/uv/certifi i stary magazyn CA. Niczego nie
opublikowano ani nie wdrożono na produkcję. Pełnej remediacji nie potwierdzono.

## Lokalne dowody

W worktree spx-examples: `build-security-smoke.log`, `build-resync-final.log`,
`build-qa313-install.log`, `build-qa313-sync.log`, `build-ci-toolchain.log`,
`build-portable-package.log`, `build-portable-launch.log`, `build-image-security.log`,
`build-homeassistant-security.log`, `build-unit-tests.log`,
`build/baseline-emsign-tests.log`.
W spx-server: `build-emsign-docker.log`, `build-emsign-tests.log`,
`build-emsign-lint.log`, `build/baseline-emsign-tests.log`.

## Zmienione pliki: spx-examples

- `.github/workflows/ci-cd.yml`
- `.github/workflows/ci-nightly.yml`
- `.github/workflows/installer-smoke.yml`
- `.github/workflows/installer-stack-qualification.yml`
- `.github/workflows/protocol-qualification.yml`
- `.gitignore`
- `README.md`
- `docs/EMSIGN_6424.md`
- `installer/macos/python_runtime.sh`
- `installer/mcp_workspace.py`
- `installer/runtime_bootstrap.py`
- `packaging/windows/Build.ps1`
- `packaging/windows/README.md`
- `packaging/windows/launcher/Program.cs`
- `packaging/windows/wix/SPX.Bundle.wxs`
- `packaging/windows/wix/SPX.Product.wxs`
- `poetry.lock`
- `pyproject.toml`
- `scripts/build_macos_pkg.sh`
- `spx-install.ps1`
- `tests/installer/security_bootstrap_smoke.py`
- `tests/installer/test_ci_workflow.py`
- `tests/installer/test_installer_smoke_workflow.py`
- `tests/installer/test_macos_installer_ci.py`
- `tests/installer/test_macos_python_runtime.py`
- `tests/installer/test_mcp_workspace.py`
- `tests/installer/test_python_image_security.py`
- `tests/installer/test_runtime_bootstrap.py`
- `tests/installer/test_windows_installer_ci.py`
- `tools/secure_ci_python.py`
- `tools/verify_python_images.py`

## Zmienione pliki: spx-server

- `.github/workflows/ci-cd.yml`
- `Dockerfile`
- `EMSIGN_6424.md`
- `README.md`
- `poetry.lock`
- `pyproject.toml`
- `scripts/secure_python.py`
- `tests/test_package_security.py`

## Sumy lokalnych archiwów QA

- `spx-installer-0.0.0-emsign-qa.ps1`: SHA-256 `730d231af8374021f182b68d1c11883fcd169a8966305e5f1847a39ceb66ae96`
- `spx-installer-0.0.0-emsign-qa.run`: SHA-256 `43c1a8ee6d4ef597f34b936706e9be78e06d0bd203d296c9207209db8c30d742`
- `spx-installer-0.0.0-emsign-qa.tgz`: SHA-256 `9ad547ec81d9ba8e0e14dc2d5b3079719945178e75458b8a7270d9d1d8a6046a`
