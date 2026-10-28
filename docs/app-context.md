# AppContext runtime ownership

`AppContext` is the application composition root for runtime services and source instances.

Transport and UI code must access runtime-owned dependencies through the active context (`get_app_context()`) rather than importing module-level service singletons or compatibility proxies. Pure rendering helpers should receive concrete services explicitly when they need them.

This keeps lifecycle ownership centralized, makes shutdown/resource cleanup predictable, and prevents import-time construction of network/source services.
