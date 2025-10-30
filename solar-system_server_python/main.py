"""Solar system MCP server implemented with the Python FastMCP helper."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.provider import TokenVerifier, AccessToken

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import jwt
from jwt import PyJWKClient
import httpx

import logging

# 모듈 레벨 logger 생성 (권장)
logger = logging.getLogger(__name__)

# ===== 인증 설정 (하드코딩) =====
AUTH_ENABLED = True  # 인증 활성화 여부 (개발 시 False로 변경 가능)
AUTH_ISSUER_URL = "https://web-production-941fc.up.railway.app"
AUTH_JWKS_URL = "https://auth.com/.well-known/jwks.json"
AUTH_AUDIENCE = "https://solar-system.example.com/mcp"
AUTH_RESOURCE_SERVER_URL = "https://solar-system.example.com/mcp"
AUTH_REQUIRED_SCOPE = "solar:read"



MIME_TYPE = "text/html+skybridge"
PLANETS = [
    "Mercury",
    "Venus",
    "Earth",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
]
PLANET_ALIASES = {
    "terra": "Earth",
    "gaia": "Earth",
    "soliii": "Earth",
    "tellus": "Earth",
    "ares": "Mars",
    "jove": "Jupiter",
    "zeus": "Jupiter",
    "cronus": "Saturn",
    "ouranos": "Uranus",
    "poseidon": "Neptune",
}
PLANET_DESCRIPTIONS = {
    "Mercury": "Mercury is the smallest planet in the Solar System and the closest to the Sun. It has a rocky, cratered surface and extreme temperature swings.",
    "Venus": "Venus, similar in size to Earth, is cloaked in thick clouds of sulfuric acid with surface temperatures hot enough to melt lead.",
    "Earth": "Earth is the only known planet to support life, with liquid water covering most of its surface and a protective atmosphere.",
    "Mars": "Mars, the Red Planet, shows evidence of ancient rivers and volcanoes and is a prime target in the search for past life.",
    "Jupiter": "Jupiter is the largest planet, a gas giant with a Great Red Spot—an enormous storm raging for centuries.",
    "Saturn": "Saturn is famous for its stunning ring system composed of billions of ice and rock particles orbiting the planet.",
    "Uranus": "Uranus is an ice giant rotating on its side, giving rise to extreme seasonal variations during its long orbit.",
    "Neptune": "Neptune, the farthest known giant, is a deep-blue world with supersonic winds and a faint ring system.",
}
DEFAULT_PLANET = "Earth"


# ===== 인증 설정 =====
class SolarSystemTokenVerifier(TokenVerifier):
    """
    JWT 토큰을 검증하는 커스텀 verifier.
    Auth Server (https://auth.com)에서 발급된 토큰을 검증합니다.
    """
    
    def __init__(self):
        # Auth Server 설정
        self.jwks_url = AUTH_JWKS_URL
        self.issuer = AUTH_ISSUER_URL
        self.audience = AUTH_AUDIENCE
        self.required_scope = AUTH_REQUIRED_SCOPE
        
        logger.info(f"Initializing token verifier with issuer: {self.issuer}")
        logger.info(f"JWKS URL: {self.jwks_url}")
        logger.info(f"Required scope: {self.required_scope}")
        
        # PyJWKClient 초기화 (공개 키 캐싱)
        self.jwks_client = PyJWKClient(self.jwks_url)
    
    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """
        JWT 토큰을 검증하고 AccessToken 객체를 반환합니다.
        
        Args:
            token: Bearer 토큰 문자열
            
        Returns:
            AccessToken 객체 또는 검증 실패 시 None
        """
        try:
            # JWKS에서 서명 키 가져오기
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            
            # JWT 디코드 및 검증
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                }
            )
            
            # 필수 권한 확인
            scopes = payload.get("scope", "").split() if isinstance(payload.get("scope"), str) else payload.get("permissions", [])
            
            # 필수 scope 검증
            if self.required_scope not in scopes:
                logger.warning(f"Token missing required scope '{self.required_scope}'. Scopes: {scopes}")
                return None
            
            # AccessToken 객체 생성
            logger.info(f"Token verified successfully for subject: {payload.get('sub', 'unknown')}")
            return AccessToken(
                token=token,
                client_id=payload.get("azp", payload.get("client_id", "")),
                subject=payload.get("sub", ""),
                scopes=scopes,
                claims=payload,
            )
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None


@dataclass(frozen=True)
class SolarWidget:
    identifier: str
    title: str
    template_uri: str
    invoking: str
    invoked: str
    html: str
    response_text: str


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


@lru_cache(maxsize=None)
def _load_widget_html(component_name: str) -> str:
    html_path = ASSETS_DIR / f"{component_name}.html"
    logger.info(f"loading html file: {html_path}")
    if html_path.exists():
        logger.info(f"html 파일 찾았음. {component_name}")
        return html_path.read_text(encoding="utf8")
    else:
        logger.info(f"html 없음: {component_name} ")
    fallback_candidates = sorted(ASSETS_DIR.glob(f"{component_name}-*.html"))
    if fallback_candidates:
        return fallback_candidates[-1].read_text(encoding="utf8")

    raise FileNotFoundError(
        f'Widget HTML for "{component_name}" not found in {ASSETS_DIR}. '
        "Run `pnpm run build` to generate the assets before starting the server."
    )



WIDGET = SolarWidget(
    identifier="solar-system",
    title="Explore the Solar System",
    template_uri="ui://widget/solar-system_v2.html", # 동작함(default, 문서에서 제공되는 형태)
    # template_uri="my_custom_template_uri_test", -> 동작하지 않음
    # template_uri="ui://my-custom-template-uri-test", - 동작함
    # template_uri="custom://my-custom-template-uri-test", -> 동작하지 않음
    # template_uri="ui+solar://my-custom-template-uri-test", -> 동작함. prefix를 ui로 하는 경우에 동작함(스킴 형태를 유지한다는 가정 하에)
    invoking="Charting the solar system",
    invoked="Solar system ready",
    html=_load_widget_html("solar-system"),
    response_text="Solar system ready",
)


class SolarInput(BaseModel):
    """Schema describing the solar system focus request."""

    planet_name: str = Field(
        DEFAULT_PLANET,
        alias="planetName",
        description="Planet to focus in the widget (case insensitive).",
    )
    auto_orbit: bool = Field(
        True,
        alias="autoOrbit",
        description="Whether to keep the camera orbiting if the target planet is missing.",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# FastMCP 초기화 with 선택적 인증 설정
if AUTH_ENABLED:
    logger.info("=== Authentication is ENABLED ===")
    logger.info(f"Issuer: {AUTH_ISSUER_URL}")
    logger.info(f"Resource Server: {AUTH_RESOURCE_SERVER_URL}")
    logger.info(f"Required Scope: {AUTH_REQUIRED_SCOPE}")
    
    mcp = FastMCP(
        name="solar-system-python",
        stateless_http=True,
        token_verifier=SolarSystemTokenVerifier(),
        auth=AuthSettings(
            issuer_url=AUTH_ISSUER_URL,
            resource_server_url=AUTH_RESOURCE_SERVER_URL,
            required_scopes=[AUTH_REQUIRED_SCOPE],
        ),
    )
else:
    logger.warning("=== Authentication is DISABLED - For development only! ===")
    mcp = FastMCP(
        name="solar-system-python",
        stateless_http=True,
    )

TOOL_INPUT_SCHEMA: Dict[str, Any] = SolarInput.model_json_schema()


def _resource_description(widget: SolarWidget) -> str:
    return f"{widget.title} widget markup"


def _tool_meta(widget: SolarWidget) -> Dict[str, Any]:
    return {
        "openai/outputTemplate": widget.template_uri,
        "openai/toolInvocation/invoking": widget.invoking,
        "openai/toolInvocation/invoked": widget.invoked,
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
        "annotations": {
          "destructiveHint": False,
          "openWorldHint": False,
          "readOnlyHint": True,
        }
    }


def _embedded_widget_resource(widget: SolarWidget) -> types.EmbeddedResource:
    return types.EmbeddedResource(
        type="resource",
        resource=types.TextResourceContents(
            uri=widget.template_uri,
            mimeType=MIME_TYPE,
            text=widget.html,
            title=widget.title,
        ),
    )


def _normalize_planet(name: str) -> str | None:
    if not name:
        return DEFAULT_PLANET

    key = name.strip().lower()
    if not key:
        return DEFAULT_PLANET

    clean = ''.join(ch for ch in key if ch.isalnum())

    for planet in PLANETS:
        planet_key = ''.join(ch for ch in planet.lower() if ch.isalnum())
        if clean == planet_key or key == planet.lower():
            return planet

    alias = PLANET_ALIASES.get(clean)
    if alias:
        return alias

    for planet in PLANETS:
        planet_key = ''.join(ch for ch in planet.lower() if ch.isalnum())
        if planet_key.startswith(clean):
            return planet

    return None


@mcp._mcp_server.list_tools()
async def _list_tools() -> List[types.Tool]:
    logger.info("도구 목록 조회 호출됨!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    
    # 인증이 활성화된 경우에만 securitySchemes 추가
    security_schemes = None
    if AUTH_ENABLED:
        security_schemes = [
            types.SecurityScheme(
                type="oauth2",
                scopes=[AUTH_REQUIRED_SCOPE],
            )
        ]
    
    return [
        types.Tool(
            name="focus-solar-planet",
            title=WIDGET.title,
            description="Render the solar system widget centered on the requested planet.",
            inputSchema=TOOL_INPUT_SCHEMA,
            securitySchemes=security_schemes,
            _meta=_tool_meta(WIDGET),
        )
    ]


# list_resources, list_resource_templates -> 이 함수들은 구현/등록이 되어있지 않아도 App이 일단은 동작함
# -> 이 친구들이 필요한 포인트는 어딘지 파악해볼 필요가 있음.
# @mcp._mcp_server.list_resources()
# async def _list_resources() -> List[types.Resource]:
#     logger.info("리소스 목록 조회 호출됨!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
#     return [
#         types.Resource(
#             name=WIDGET.title,
#             title=WIDGET.title,
#             uri=WIDGET.template_uri,
#             description=_resource_description(WIDGET),
#             mimeType=MIME_TYPE,
#             _meta=_tool_meta(WIDGET),
#         )
#     ]


# @mcp._mcp_server.list_resource_templates()
# async def _list_resource_templates() -> List[types.ResourceTemplate]:
#     logger.info("리소스 템플릿 목록 조회 호출됨!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
#     return [
#         types.ResourceTemplate(
#             name=WIDGET.title,
#             title=WIDGET.title,
#             uriTemplate=WIDGET.template_uri,
#             description=_resource_description(WIDGET),
#             mimeType=MIME_TYPE,
#             _meta=_tool_meta(WIDGET),
#         )
#     ]


async def _handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
    resource_uri = str(req.params.uri)

    logger.info("리소스 목록 READ 호출됨!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    logger.info(f"요청 정보: {resource_uri}")

    if resource_uri != WIDGET.template_uri:
        return types.ServerResult(
            types.ReadResourceResult(
                contents=[],
                _meta={"error": f"Unknown resource: {req.params.uri}"},
            )
        )

    contents = [
        types.TextResourceContents(
            uri=WIDGET.template_uri,
            mimeType=MIME_TYPE,
            text=WIDGET.html,
            _meta=_tool_meta(WIDGET),
        )
    ]

    return types.ServerResult(types.ReadResourceResult(contents=contents))


async def _call_tool_request(req: types.CallToolRequest) -> types.ServerResult:
    arguments = req.params.arguments or {}
    try:
        payload = SolarInput.model_validate(arguments)
    except ValidationError as exc:
        return types.ServerResult(
            types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Input validation error: {exc.errors()}",
                    )
                ],
                isError=True,
            )
        )

    planet = _normalize_planet(payload.planet_name)
    if planet is None:
        return types.ServerResult(
            types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            "Unknown planet. Provide one of: "
                            + ", ".join(PLANETS)
                        ),
                    )
                ],
                isError=True,
            )
        )

    widget_resource = _embedded_widget_resource(WIDGET)
    meta: Dict[str, Any] = {
        "openai.com/widget": widget_resource.model_dump(mode="json"),
        "openai/outputTemplate": WIDGET.template_uri,
        "openai/toolInvocation/invoking": WIDGET.invoking,
        "openai/toolInvocation/invoked": WIDGET.invoked,
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    description = PLANET_DESCRIPTIONS.get(planet, "")
    structured = {
        "planet_name": planet,
        "planet_description": description,
        "autoOrbit": payload.auto_orbit,
    }
    message = f"Centered the solar system view on {planet}."

    return types.ServerResult(
        types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=message,
                )
            ],
            structuredContent=structured,
            _meta=meta,
        )
    )


mcp._mcp_server.request_handlers[types.CallToolRequest] = _call_tool_request
mcp._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource

app = mcp.streamable_http_app()

try:
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
except Exception:  # pragma: no cover - middleware is optional
    pass

# 정적 파일 서빙 추가 (JS/CSS assets)
try:
    from starlette.staticfiles import StaticFiles
    
    if ASSETS_DIR.exists():
        # /assets 경로에 정적 파일 제공
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="static")
        logger.info(f"Static files mounted at /assets from {ASSETS_DIR}")
    else:
        logger.warning(f"Assets directory not found: {ASSETS_DIR}")
except Exception as e:
    logger.error(f"Failed to mount static files: {e}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
