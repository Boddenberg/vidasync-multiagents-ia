from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.services.image_reference_resolver import (
    resolve_image_reference_to_public_url,
)


def test_resolve_image_reference_keeps_http_url() -> None:
    url = "https://example.com/image.jpg"
    resolved = resolve_image_reference_to_public_url(
        url,
        supabase_url="https://project.supabase.co",
        public_bucket="pipeline-inputs",
    )
    assert resolved == url


def test_resolve_image_reference_keeps_signed_url() -> None:
    signed_url = (
        "https://project.supabase.co/storage/v1/object/sign/"
        "pipeline-inputs/file/abc/image.jpg?token=expired"
    )
    resolved = resolve_image_reference_to_public_url(
        signed_url,
        supabase_url="https://project.supabase.co",
        public_bucket="pipeline-inputs",
    )
    assert resolved == signed_url


def test_resolve_image_reference_keeps_authenticated_url() -> None:
    authenticated_url = (
        "https://project.supabase.co/storage/v1/object/authenticated/"
        "pipeline-inputs/file/abc/image.jpg"
    )
    resolved = resolve_image_reference_to_public_url(
        authenticated_url,
        supabase_url="https://project.supabase.co",
        public_bucket="pipeline-inputs",
    )
    assert resolved == authenticated_url


def test_resolve_image_reference_builds_public_url_from_key() -> None:
    resolved = resolve_image_reference_to_public_url(
        "file/abc/2026-03-08/image.jpg",
        supabase_url="https://project.supabase.co",
        public_bucket="pipeline-inputs",
    )
    assert (
        resolved
        == "https://project.supabase.co/storage/v1/object/public/pipeline-inputs/file/abc/2026-03-08/image.jpg"
    )


def test_resolve_image_reference_handles_key_with_bucket_prefix() -> None:
    resolved = resolve_image_reference_to_public_url(
        "pipeline-inputs/file/abc/image.jpg",
        supabase_url="https://project.supabase.co",
        public_bucket="pipeline-inputs",
    )
    assert resolved == "https://project.supabase.co/storage/v1/object/public/pipeline-inputs/file/abc/image.jpg"


def test_resolve_image_reference_raises_when_missing_supabase_url_for_key() -> None:
    try:
        resolve_image_reference_to_public_url(
            "file/abc/image.jpg",
            supabase_url="",
            public_bucket="pipeline-inputs",
        )
        assert False, "Esperava ServiceError por SUPABASE_URL ausente."
    except ServiceError as exc:
        assert exc.status_code == 500
        assert "SUPABASE_URL" in exc.message
