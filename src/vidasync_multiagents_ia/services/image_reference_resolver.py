import re

from vidasync_multiagents_ia.core import ServiceError


def resolve_image_reference_to_public_url(
    image_reference: str,
    *,
    supabase_url: str,
    public_bucket: str,
) -> str:
    raw = (image_reference or "").strip()
    if not raw:
        raise ServiceError("Campo 'imagem_url' e obrigatorio.", status_code=400)

    lowered = raw.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        # /**** Preserva URLs assinadas/autenticadas para nao perder token de acesso. ****/
        return raw

    bucket_value = (public_bucket or "").strip().strip("/")
    if not bucket_value:
        raise ServiceError("Configuracao de bucket publico ausente para resolver imagem.", status_code=500)

    base_url = (supabase_url or "").strip().rstrip("/")
    if not base_url:
        raise ServiceError(
            "SUPABASE_URL nao configurada para resolver referencia de imagem sem URL.",
            status_code=500,
        )

    key = raw.lstrip("/")
    if key.startswith(f"{bucket_value}/"):
        key = key[len(bucket_value) + 1 :]

    # /**** Normaliza barras para evitar URLs invalidas com '//' internos no path. ****/
    key = re.sub(r"/{2,}", "/", key).strip("/")
    if not key:
        raise ServiceError("Referencia de imagem invalida.", status_code=400)

    return f"{base_url}/storage/v1/object/public/{bucket_value}/{key}"
