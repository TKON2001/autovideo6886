import base64
import json
import re
from pathlib import Path

from openai import OpenAI

from config import get_settings
from opc_loader import load_opc_context


settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)

VIDEO_MODES = {
    "deep": {
        "label": "video chuyên sâu",
        "min_scenes": 8,
        "max_scenes": 10,
        "estimated_duration_sec": 120,
        "duration_goal": "Tạo video dài khoảng 90 đến 150 giây.",
        "narration_words": "35 đến 60",
        "style_note": (
            "Kể sâu, có chiều sâu tư duy, có mạch documentary và một khoảnh "
            "khắc nhận ra rõ ràng."
        ),
    },
    "standard": {
        "label": "video tiêu chuẩn",
        "min_scenes": 6,
        "max_scenes": 8,
        "estimated_duration_sec": 80,
        "duration_goal": "Tạo video tiêu chuẩn khoảng 60 đến 90 giây.",
        "narration_words": "25 đến 45",
        "style_note": (
            "Ưu tiên sự rõ ràng, chính xác, dễ hiểu; có hook tốt, nhịp dựng "
            "gọn và hình ảnh cinematic vừa đủ."
        ),
    },
    "quick": {
        "label": "video nhanh",
        "min_scenes": 4,
        "max_scenes": 6,
        "estimated_duration_sec": 50,
        "duration_goal": "Tạo video ngắn khoảng 35 đến 60 giây.",
        "narration_words": "20 đến 35",
        "style_note": (
            "Đi thẳng vào ý chính, mở đầu mạnh, nhịp nhanh, phù hợp test ý "
            "tưởng hoặc tiết kiệm quota."
        ),
    },
    "story": {
        "label": "video kể chuyện",
        "min_scenes": 8,
        "max_scenes": 10,
        "estimated_duration_sec": 100,
        "duration_goal": "Tạo video kể chuyện khoảng 80 đến 120 giây.",
        "narration_words": "30 đến 50",
        "style_note": (
            "Ưu tiên cấu trúc câu chuyện: bối cảnh, xung đột, bước ngoặt, cao "
            "trào và kết lại bằng dư âm cảm xúc."
        ),
    },
    "fact": {
        "label": "video giải thích",
        "min_scenes": 6,
        "max_scenes": 8,
        "estimated_duration_sec": 75,
        "duration_goal": "Tạo video giải thích khoảng 60 đến 90 giây.",
        "narration_words": "25 đến 45",
        "style_note": (
            "Ưu tiên sự rõ ràng, chính xác, dễ hiểu; giải thích nguyên nhân, "
            "hệ quả, ví dụ và ý nghĩa thực tế."
        ),
    },
    "premium": {
        "label": "video premium điện ảnh",
        "min_scenes": 10,
        "max_scenes": 12,
        "estimated_duration_sec": 140,
        "duration_goal": "Tạo video premium khoảng 100 đến 150 giây.",
        "narration_words": "35 đến 60",
        "style_note": (
            "Ưu tiên chất lượng điện ảnh, hình ảnh giàu cảm xúc, nhịp kể chắc, "
            "mở đầu mạnh và kết thúc có dư âm rõ ràng."
        ),
    },
}


def get_video_mode(mode: str) -> dict:
    normalized_mode = (mode or "deep").lower().strip()
    if normalized_mode == "quality_standard":
        normalized_mode = "standard"
    if normalized_mode == "quality_deep":
        normalized_mode = "deep"
    if normalized_mode == "quality_premium":
        normalized_mode = "premium"
    return VIDEO_MODES.get(normalized_mode, VIDEO_MODES["deep"])


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "AI trả về kịch bản không đúng định dạng JSON. "
                    "Vui lòng thử lại với chủ đề ngắn và rõ hơn."
                ) from exc

        raise ValueError(
            "AI không trả về JSON hợp lệ. Vui lòng thử lại với chủ đề ngắn và rõ hơn."
        ) from None


def create_video_plan(topic: str, mode: str = "deep") -> dict:
    mode_config = get_video_mode(mode)
    min_scenes = mode_config["min_scenes"]
    max_scenes = mode_config["max_scenes"]
    opc_context = load_opc_context()

    prompt = f"""
Bạn là một đạo diễn sáng tạo, biên kịch documentary và art director cho video AI.

Nhiệm vụ của bạn là biến một chủ đề đơn giản thành một video dọc 9:16 có cấu trúc,
có chiều sâu, có cảm xúc, có nhịp dựng rõ ràng và có hình ảnh minh họa điện ảnh
đủ mạnh để giữ chân người xem trên TikTok, Reels và YouTube Shorts.

CHỦ ĐỀ VIDEO:
"{topic}"

CHẾ ĐỘ KỊCH BẢN:
- Loại video: {mode_config["label"]}.
- {mode_config["duration_goal"]}
- Định hướng riêng: {mode_config["style_note"]}

AUTO VIDEO OPC CONTEXT:
Các tài liệu vận hành dưới đây là luật ưu tiên khi tạo kịch bản. Hãy tuân thủ
chúng trong mọi cảnh, đặc biệt là tiêu chuẩn video dọc 9:16, hình ảnh cinematic,
caption dễ đọc trên điện thoại và không có logo/watermark/nhãn cảnh.

{opc_context}

LUẬT OPC BẮT BUỘC:
- Video phải là vertical 9:16.
- Kịch bản phải có strong hook, cấu trúc cảnh rõ và mạch kể tự nhiên.
- image_prompt phải cinematic, chi tiết, bằng tiếng Anh.
- Không tạo text bên trong ảnh AI.
- Không watermark.
- Không logo.
- Không corner scene label.
- Caption phải ngắn, dễ đọc trên mobile.
- Output cuối cùng chỉ được là JSON hợp lệ, không markdown, không giải thích.

MỤC TIÊU VIDEO:
- {mode_config["duration_goal"]}
- Không làm video quá hời hợt.
- Không viết kiểu sáo rỗng, motivational rẻ tiền, hoặc liệt kê thông tin khô cứng.
- Video phải có mạch dựng rõ ràng: hook, bối cảnh, vấn đề, đào sâu, cao trào,
  kết luận.
- Nội dung phải đủ dễ hiểu cho người phổ thông nhưng vẫn có chiều sâu tư duy.
- Mỗi cảnh phải có hình ảnh minh họa điện ảnh, đẹp, giàu cảm xúc, có bố cục,
  ánh sáng, không khí và vai trò kể chuyện rõ ràng.

PHONG CÁCH KỊCH BẢN:
- Giọng kể: sâu sắc, cuốn hút, thông minh, có nhịp điệu.
- Không dùng câu quá dài.
- Không dùng từ ngữ quá học thuật nếu không cần thiết.
- Mỗi cảnh nên có một ý chính rõ ràng.
- Các cảnh phải nối với nhau tự nhiên, không rời rạc.
- Ưu tiên cách kể theo hướng: "vì sao điều này quan trọng?" thay vì chỉ
  "điều này là gì?".
- Nếu chủ đề là lịch sử/khoa học/xã hội: hãy giải thích nguyên nhân, hệ quả,
  bối cảnh và ý nghĩa.
- Nếu chủ đề là đạo lý/cuộc sống: tránh giáo điều, hãy dùng quan sát thực tế,
  nghịch lý, ví dụ và kết luận sâu.

CẤU TRÚC VIDEO BẮT BUỘC:
Tạo từ {min_scenes} đến {max_scenes} cảnh.

Mỗi cảnh phải gồm:
1. caption:
   - Dòng chữ ngắn hiện trên màn hình.
   - Tối đa 12 từ.
   - Có lực, dễ nhớ, không nhạt.

2. narration:
   - Lời thuyết minh cho cảnh đó.
   - Mỗi cảnh khoảng {mode_config["narration_words"]} từ.
   - Viết tự nhiên như người dẫn chuyện chuyên nghiệp.
   - Có nhịp kể, có cảm xúc, không khô.

3. image_prompt:
   - Prompt hình ảnh minh họa bằng tiếng Anh.
   - Phải cực kỳ chi tiết để tạo ảnh AI chất lượng cao.
   - Bắt buộc có các cụm/ý sau:
     vertical 9:16 cinematic composition,
     cinematic realism,
     realistic lighting,
     emotional atmosphere,
     detailed subject,
     detailed environment,
     depth of field,
     high detail,
     professional color grading,
     no text,
     no watermark,
     no logo,
     no subtitles,
     no UI elements.
   - Mô tả rõ subject chính, bối cảnh, bố cục khung hình dọc, ánh sáng, màu sắc,
     cảm xúc, phong cách điện ảnh, góc máy, độ sâu trường ảnh và chi tiết nền.
   - Không viết prompt chung chung.
   - Mỗi cảnh phải khác nhau về bố cục và cảm xúc.
   - Ví dụ phong cách viết tốt:
     "A lonely young man sitting under a large old tree on a quiet hill at sunrise,
     soft golden light, gentle wind moving the grass, wide vertical cinematic
     composition, emotional atmosphere, realistic texture, shallow depth of field,
     high detail, no text, no watermark."

4. visual_note:
   - Ghi ngắn gọn vai trò của hình ảnh trong cảnh đó.
   - Ví dụ: "Thiết lập bối cảnh", "Tạo cảm giác cô đơn",
     "Minh họa sự chuyển biến", "Đẩy cao cao trào".

5. duration_sec:
   - Thời lượng đề xuất của cảnh.
   - Từ 8 đến 14 giây.

YÊU CẦU VỀ CHIỀU SÂU:
- Video phải trả lời được 3 lớp:
  1. Người xem đang thấy gì?
  2. Điều đó thực sự có nghĩa là gì?
  3. Vì sao họ nên quan tâm?
- Phải có ít nhất một đoạn tạo "khoảnh khắc nhận ra" cho người xem.
- Không được chỉ đưa thông tin bề mặt.
- Không được viết kiểu "Bạn có biết..." quá phổ thông trừ khi thật sự cần.
- Tránh các câu chung chung như:
  "Điều này rất quan trọng"
  "Chúng ta cần cố gắng"
  "Cuộc sống là một hành trình"
  "Hãy luôn tin vào bản thân"
- Nếu có thông điệp cuối, nó phải cụ thể, sắc và đáng nhớ.

YÊU CẦU VỀ HÌNH ẢNH:
- Mỗi image_prompt phải tạo được một cảnh minh họa khác nhau.
- Không lặp lại cùng một kiểu hình ảnh.
- Hình ảnh phải có tính kể chuyện, không chỉ là ảnh nền đẹp.
- Bắt buộc có vertical 9:16 cinematic composition, cinematic realism,
  realistic lighting, realistic texture, depth of field, dramatic composition,
  emotional atmosphere, high detail, professional color grading.
- Không đưa chữ vào hình.
- Không watermark, logo, subtitles, typography hoặc UI elements.
- Không mô tả ảnh quá chung chung. Hãy viết như một art director chuyên nghiệp.

FORMAT TRẢ VỀ:
Chỉ trả về JSON hợp lệ.
Không markdown.
Không giải thích thêm.
Không dùng ```json.

Schema bắt buộc:

{{
  "title": "Tiêu đề video ngắn gọn, hấp dẫn",
  "summary": "Tóm tắt 1 câu về thông điệp chính của video",
  "tone": "Giọng điệu của video",
  "estimated_duration_sec": {mode_config["estimated_duration_sec"]},
  "scenes": [
    {{
      "caption": "Dòng chữ ngắn trên màn hình",
      "narration": "Lời thuyết minh sâu sắc cho cảnh này.",
      "image_prompt": "Highly detailed cinematic image prompt in English, no text, no watermark...",
      "visual_note": "Vai trò hình ảnh trong cảnh này",
      "duration_sec": 10
    }}
  ]
}}

Hãy tạo kịch bản tốt nhất có thể cho chủ đề trên.
"""

    response = client.responses.create(
        model=settings.text_model,
        input=prompt,
    )

    data = _extract_json(response.output_text)

    if "scenes" not in data or len(data["scenes"]) < min_scenes:
        raise ValueError(f"AI response must contain at least {min_scenes} scenes")

    return data


def create_voice(text: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with client.audio.speech.with_streaming_response.create(
        model=settings.tts_model,
        voice=settings.tts_voice,
        input=text,
    ) as response:
        response.stream_to_file(str(output_path))

    return output_path


def create_image(image_prompt: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = f"""
Create a cinematic vertical 9:16 video background image for TikTok/Reels/Shorts.

Scene prompt:
{image_prompt}

Hard requirements:
- No text, no subtitles, no captions, no logo, no watermark, no typography.
- Vertical 9:16 cinematic composition.
- Cinematic realism with realistic lighting and professional color grading.
- Strong subject, atmosphere, lighting, depth, and visual storytelling.
- Detailed subject and detailed environment.
- Emotional atmosphere, depth of field, high detail.
- Leave clean lower-third space where an overlaid video caption can remain readable.
"""

    response = client.images.generate(
        model=settings.image_model,
        prompt=prompt,
        size=settings.image_size,
        quality=settings.image_quality,
        n=1,
    )

    image_base64 = response.data[0].b64_json
    if not image_base64:
        raise ValueError("Image generation response did not contain b64_json")

    output_path.write_bytes(base64.b64decode(image_base64))
    return output_path
