# Solar System 3D Viewer

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A 3D interactive solar system viewer built with React and Three.js, designed to work with the Apps SDK and MCP (Model Context Protocol).

## MCP + Apps SDK overview

The Model Context Protocol (MCP) is an open specification for connecting large language model clients to external tools, data, and user interfaces. An MCP server exposes tools that a model can call during a conversation and returns results according to the tool contracts. Those results can include extra metadata—such as inline HTML—that the Apps SDK uses to render rich UI components (widgets) alongside assistant messages.

Within the Apps SDK, MCP keeps the server, model, and UI in sync. By standardizing the wire format, authentication, and metadata, it lets ChatGPT reason about your connector the same way it reasons about built-in tools.

## Repository structure

- `src/solar-system/` – Solar system widget source code
- `assets/` – Generated HTML, JS, and CSS bundles after running the build step
- `solar-system_server_python/` – Python MCP server for the 3D solar system widget
- `build-all.mts` – Vite build orchestrator that produces hashed bundles for the widget

## Prerequisites

- Node.js 18+
- pnpm (recommended) or npm/yarn
- Python 3.10+ (for the Python MCP server)

## Install dependencies

Clone the repository and install the workspace dependencies:

```bash
pnpm install
```

> Using npm or yarn? Install the root dependencies with your preferred client and adjust the commands below accordingly.

## Build the widget

The solar system widget is bundled into standalone assets that the MCP server serves as a reusable UI resource.

```bash
pnpm run build
```

This command runs `build-all.mts`, producing versioned `.html`, `.js`, and `.css` files inside `assets/`. The widget is wrapped with the CSS it needs so you can host the bundles directly or ship them with your own server.

To iterate on the widget locally, you can also launch the Vite dev server:

```bash
pnpm run dev
```

## Serve the static assets

If you want to preview the generated bundles without the MCP server, start the static file server after running a build:

```bash
pnpm run serve
```

The assets are exposed at [`http://localhost:4444`](http://localhost:4444) with CORS enabled so that local tooling (including MCP inspectors) can fetch them.

## Run the MCP server

The repository includes a Python MCP server that serves the solar system widget.

### Solar system Python server

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r solar-system_server_python/requirements.txt
uvicorn solar-system_server_python.main:app --port 8000
```

Every tool response includes plain text content, structured JSON, and `_meta.openai/outputTemplate` metadata so the Apps SDK can hydrate the matching widget.

## Testing in ChatGPT

To add this app to ChatGPT, enable [developer mode](https://platform.openai.com/docs/guides/developer-mode), and add your app in Settings > Connectors.

To add your local server without deploying it, you can use a tool like [ngrok](https://ngrok.com/) to expose your local server to the internet.

For example, once your MCP server is running, you can run:

```bash
ngrok http 8000
```

You will get a public URL that you can use to add your local server to ChatGPT in Settings > Connectors.

For example: `https://<custom_endpoint>.ngrok-free.app/mcp`

Once you add a connector, you can use it in ChatGPT conversations.

You can add your app to the conversation context by selecting it in the "More" options.

You can then invoke tools by asking something related to the solar system, such as "Show me the solar system" or "What does Jupiter look like?".

## Next steps

- Customize the widget data: edit the handlers in `solar-system_server_python/main.py` to fetch data from your systems.
- Create your own components: add new entries into `src/` and they will be picked up automatically by the build script.

### Deploy your MCP server

You can use the cloud environment of your choice to deploy your MCP server.

Include this in the environment variables:

```
BASE_URL=https://your-server.com
```

This will be used to generate the HTML for the widget so that it can serve static assets from this hosted URL.

## Contributing

You are welcome to open issues or submit PRs to improve this app, however, please note that we may not review all suggestions.

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE) for details.
