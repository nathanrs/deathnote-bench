"""One model call that returns a JSON object, with token counts, time and any reasoning summary."""
import json
import re
import time


def parse(text):
    match = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}


def ask(model, system, user, effort="low"):
    provider, _, name = model.partition("/")
    started = time.time()
    for attempt in range(3):
        try:
            if provider == "anthropic":
                import anthropic
                with anthropic.Anthropic().messages.stream(
                    model=name, max_tokens=32000, system=system, thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": effort}, messages=[{"role": "user", "content": user}],
                ) as stream:
                    reply = stream.get_final_message()
                text = "".join(block.text for block in reply.content if block.type == "text")
                reasoning = "\n".join(getattr(block, "thinking", "") or "" for block in reply.content if block.type == "thinking")
            else:
                import openai
                reply = openai.OpenAI().responses.create(
                    model=name, instructions=system, input=user, reasoning={"effort": effort, "summary": "auto"}, store=False,
                )
                text = reply.output_text
                reasoning = "\n".join(part.text for item in reply.output if item.type == "reasoning" for part in item.summary or [])
            result = parse(text)
            if result:
                return {**result, "_meta": {
                    "input_tokens": reply.usage.input_tokens, "output_tokens": reply.usage.output_tokens,
                    "seconds": round(time.time() - started, 1), "reasoning": reasoning,
                }}
        except Exception as error:
            if attempt == 2:
                return {"_error": str(error)[:200]}
            time.sleep(5 * (attempt + 1))
    return {}
