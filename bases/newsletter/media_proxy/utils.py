import asyncio
import random
from io import BytesIO

import structlog
from opentelemetry import trace
from PIL import Image, ImageDraw

from .settings import MediaProxySettings


class MediaProxyUtils:
    def __init__(self, settings: MediaProxySettings):
        self.tracer: trace.Tracer = trace.get_tracer("media_proxy.utils")
        self.logger: structlog.BoundLogger = structlog.get_logger("media_proxy.utils")
        self.settings: MediaProxySettings = settings

    async def extract_first_frame(self, video_url: str) -> bytes:
        with self.tracer.start_as_current_span("extract_first_frame") as span:
            span.set_attribute("video_url", video_url)
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                video_url,
                "-vframes",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(
                    "failed_to_extract_frame",
                    video_url=video_url,
                    error=stderr.decode(),
                )
                raise RuntimeError("Failed to extract frame")

            return stdout

    def add_play_overlay(self, frame_bytes: bytes) -> bytes:
        with self.tracer.start_as_current_span("add_play_overlay") as span:
            with Image.open(BytesIO(frame_bytes)).convert("RGBA") as base_image:
                width, height = base_image.size
                span.set_attribute("width", width)
                span.set_attribute("height", height)
                request_logger = self.logger.bind(width=width, height=height)

                icon_size = int(
                    min(width, height) * self.settings.play_icon_size_percent / 100
                )
                if icon_size < 30:
                    icon_size = 30
                span.set_attribute("icon_size", icon_size)
                request_logger.info("icon_size_calculated", icon_size=icon_size)

                scale = 4
                corner_radius = icon_size // 8

                fill_color = (255, 255, 255, 160)
                high_res_overlay = Image.new(
                    "RGBA", (width * scale, height * scale), (0, 0, 0, 0)
                )
                draw = ImageDraw.Draw(high_res_overlay)

                center_x, center_y = (width * scale) // 2, (height * scale) // 2
                h = icon_size * scale
                d = h / 2
                A = (center_x - d, center_y - h // 2)  # Верхний левый
                B = (center_x - d, center_y + h // 2)  # Нижний левый
                C = (center_x + d, center_y)  # Справа

                draw.polygon(
                    [A, B, C],
                    fill=fill_color,
                    width=corner_radius * scale,
                )
                overlay = high_res_overlay.resize(
                    (width, height), resample=Image.Resampling.LANCZOS
                )
                combined = Image.alpha_composite(base_image, overlay)

                out_io = BytesIO()
                combined.convert("RGB").save(out_io, format="JPEG", quality=85)
                return out_io.getvalue()

    def generate_dynamic_doc_placeholder(self) -> bytes:
        bg_color = (240, 240, 240)
        line_color = (160, 160, 160)

        img = Image.new(
            "RGB",
            (
                self.settings.document_placeholder_width,
                self.settings.document_placeholder_height,
            ),
            bg_color,
        )
        draw = ImageDraw.Draw(img)

        margin = 40
        draw.rectangle(
            [
                margin,
                margin,
                self.settings.document_placeholder_width - margin,
                self.settings.document_placeholder_height - margin,
            ],
            outline=line_color,
            width=3,
        )

        line_y = margin + 60
        while line_y < self.settings.document_placeholder_height - margin - 40:
            line_end_x = (
                self.settings.document_placeholder_width
                - margin
                - random.randint(30, 150)
            )
            draw.line(
                [(margin + 30, line_y), (line_end_x, line_y)], fill=line_color, width=2
            )
            line_y += 40

        out_io = BytesIO()
        img.save(out_io, format="JPEG", quality=70)
        return out_io.getvalue()
