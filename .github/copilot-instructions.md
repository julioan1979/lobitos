# Copilot Instructions for Portal Lobitos

## Overview
This is a multi-section Streamlit app for managing scouting group activities. The app supports multiple "secções" (sections) and "agrupamentos" (groups), each with its own Airtable backend configuration. The UI and data are dynamically adapted based on the selected section.

## Key Architectural Patterns
- **Section Context:**
  - User selects a section/group on entry. This context is stored in `st.session_state` and drives all data access and UI labels.
  - Section-specific config is loaded from `secrets.toml` blocks named `airtable_<agrupamento>_<secao>`.
  - Changing section resets session state and returns to the selector.
- **Airtable Integration:**
  - All data (users, forms, permissions) is fetched from Airtable using credentials from the current context.
  - See `lobitos/airtable_config.py` for context management and credential loading.
- **Authentication & Permissions:**
  - Login checks user email against Airtable. Permissions (admin, tesoureiro) are extracted from user records.
  - Session state keys: `role`, `user`, `permissions`.
- **Navigation & Pages:**
  - Main navigation is in `lobitos/menu.py` and uses Streamlit sidebar links.
  - Pages are in `lobitos/pages/` and expect context and permissions to be set.
  - Use `menu_with_redirect()` at the top of each page to enforce authentication and context.

## Developer Workflows
- **Run locally:**
  - `streamlit run lobitos/app.py`
  - Requires a valid `.streamlit/secrets.toml` with all needed Airtable keys.
- **Add a new section:**
  - Add a new `[airtable_<agrupamento>_<secao>]` block to `secrets.toml`.
  - No code changes needed if following the config pattern.
- **Add a new page:**
  - Place a new file in `lobitos/pages/` and add a link in `menu.py`.
- **Debug context:**
  - Use `st.write(st.session_state)` in any page to inspect current context and permissions.

## Project Conventions
- All user-facing text is in Portuguese.
- Use `context_labels()` and `resolve_form_url()` for section-specific labels and URLs.
- Do not hardcode Airtable tokens or base IDs; always use the context loader.
- UI layout is wide by default, with custom sidebar navigation.

## Key Files
- `lobitos/airtable_config.py`: Context and config management
- `lobitos/app.py`: Entry point, login, context selection
- `lobitos/menu.py`: Sidebar navigation and session actions
- `lobitos/pages/`: Main app pages (Calendário, Voluntariado, Escuteiros, Dashboard)

---
For questions about section config or adding new features, see the README files in the root and `lobitos/` directories for more details.
