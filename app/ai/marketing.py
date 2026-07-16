"""
AI Marketing Content Generator — generates social media posts, email campaigns,
and product descriptions using local Qwen2.5 LLM.
"""

import json
import logging
from typing import Dict, List, Optional

from app.ai.local_llm import LocalLLM

logger = logging.getLogger(__name__)

# ---- Prompt Templates ----

SYSTEM_PROMPT = """Bạn là chuyên gia marketing cho một nhà máy sản xuất giày thể thao.
Hãy tạo nội dung tiếp thị chuyên nghiệp, hấp dẫn bằng tiếng Việt.
Luôn output kết quả dưới dạng JSON hợp lệ."""

FACEBOOK_POST_TEMPLATE = """Tạo 1 bài post Facebook quảng bá sản phẩm sau. Bài post nên:
- Có tiêu đề hấp dẫn
- Mô tả sản phẩm chi tiết
- Kêu gọi hành động (CTA)
- Có 3-5 hashtag

Sản phẩm: {product_name}
Thông tin thêm: {product_info}

Output JSON format:
{{"title": "...", "content": "...", "hashtags": ["#tag1", "#tag2"], "cta": "..."}}"""

EMAIL_TEMPLATE = """Viết email marketing giới thiệu sản phẩm mới. Email nên có:
- Subject line hấp dẫn
- Lời chào
- Giới thiệu sản phẩm
- Lợi ích nổi bật
- CTA button
- Chữ ký

Sản phẩm: {product_name}
Thông tin thêm: {product_info}

Output JSON format:
{{"subject": "...", "body": "...", "cta_button": "...", "signature": "..."}}"""

PRODUCT_DESC_TEMPLATE = """Viết mô tả sản phẩm chuyên nghiệp cho website thương mại điện tử:
- Tên sản phẩm
- Mô tả ngắn (1-2 câu)
- Đặc điểm nổi bật (3-5 items)
- Hướng dẫn sử dụng / bảo quản
- Giá (có thể ước lượng)

Sản phẩm: {product_name}
Thông tin thêm: {product_info}

Output JSON format:
{{"name": "...", "short_description": "...", "features": ["..."], "care_instructions": "...", "estimated_price": "..."}}"""


class MarketingGenerator:
    """AI-powered marketing content generator using local LLM."""

    def __init__(self):
        self._llm = LocalLLM()

    def generate_facebook_post(
        self, product_name: str, product_info: str = ""
    ) -> Dict:
        """Generate a Facebook post for a product."""
        prompt = FACEBOOK_POST_TEMPLATE.format(
            product_name=product_name, product_info=product_info
        )
        raw = self._llm.generate(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.8)
        return self._parse_json(raw, {
            "title": product_name,
            "content": raw,
            "hashtags": ["#giaythethao", "#sanxuatvietnam"],
            "cta": "Liên hệ ngay để biết thêm chi tiết!",
        })

    def generate_email(
        self, product_name: str, product_info: str = ""
    ) -> Dict:
        """Generate an email campaign for a product."""
        prompt = EMAIL_TEMPLATE.format(
            product_name=product_name, product_info=product_info
        )
        raw = self._llm.generate(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.7)
        return self._parse_json(raw, {
            "subject": f"Giới thiệu sản phẩm mới: {product_name}",
            "body": raw,
            "cta_button": "Xem sản phẩm",
            "signature": "Đội ngũ Marketing - Smart Factory Alpha",
        })

    def generate_product_description(
        self, product_name: str, product_info: str = ""
    ) -> Dict:
        """Generate a product description for e-commerce."""
        prompt = PRODUCT_DESC_TEMPLATE.format(
            product_name=product_name, product_info=product_info
        )
        raw = self._llm.generate(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.5)
        return self._parse_json(raw, {
            "name": product_name,
            "short_description": f"Sản phẩm {product_name} chất lượng cao",
            "features": ["Chất liệu cao cấp", "Thiết kế hiện đại"],
            "care_instructions": "Bảo quản nơi khô ráo",
            "estimated_price": "Liên hệ",
        })

    def generate_all(self, product_name: str, product_info: str = "") -> Dict:
        """Generate all marketing content for a product."""
        return {
            "product_name": product_name,
            "facebook_post": self.generate_facebook_post(product_name, product_info),
            "email": self.generate_email(product_name, product_info),
            "product_description": self.generate_product_description(product_name, product_info),
        }

    def _parse_json(self, raw: str, fallback: Dict) -> Dict:
        """Try to parse JSON from LLM output, return fallback on failure."""
        try:
            # Try to find JSON in the response
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                return json.loads(raw[start : end + 1])
            return json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse JSON from LLM output: %s", exc)
            return fallback


# ---- Convenience function ----

def generate_marketing_content(
    product_name: str, product_info: str = ""
) -> Dict:
    """Generate all marketing content for a product (convenience wrapper)."""
    gen = MarketingGenerator()
    return gen.generate_all(product_name, product_info)