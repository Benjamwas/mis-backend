"""Renderer that wraps DRF responses into the SALA success envelope.

The exception handler already builds the error envelope ({success:false,...}),
so this renderer passes those through untouched.

Success responses become:
    {"success": true, "data": <payload>, "meta": {...}}
For paginated payloads the list moves to `data` and pagination keys to `meta`.
"""
from rest_framework.renderers import JSONRenderer


class EnvelopeRenderer(JSONRenderer):
    media_type = "application/json"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, dict):
            if "success" in data:
                pass  # already an error envelope from the exception handler
            elif "data" in data and "meta" in data and len(data) == 2:
                pass  # already an envelope
            elif "results" in data:
                meta = {
                    "page": data.get("page"),
                    "page_size": data.get("page_size"),
                    "total": data.get("count"),
                    "total_pages": data.get("total_pages"),
                    "next": data.get("next"),
                    "previous": data.get("previous"),
                }
                data = {
                    "success": True,
                    "data": data.get("results", []),
                    "meta": {k: v for k, v in meta.items() if k != "results"},
                }
            else:
                data = {"success": True, "data": data, "meta": {}}
        else:
            # Non-dict payloads (strings, booleans, None) are wrapped for consistency.
            data = {"success": True, "data": data, "meta": {}}

        return super().render(data, accepted_media_type, renderer_context)