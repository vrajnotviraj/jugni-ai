from openai import AsyncOpenAI


async def call_responses(
    client: AsyncOpenAI,
    *,
    model: str,
    system: str,
    user: str,
    image_data_url: str | None = None,
    tools: list[dict[str, object]] | None = None,
) -> str:
    user_content: list[dict[str, object]] = [{"type": "input_text", "text": user}]
    if image_data_url is not None:
        user_content.append(
            {
                "type": "input_image",
                "image_url": image_data_url,
                "detail": "high",
            }
        )

    kwargs: dict[str, object] = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {"role": "user", "content": user_content},
        ],
    }
    if tools:
        kwargs["tools"] = tools

    response = await client.responses.create(**kwargs)
    return response.output_text
