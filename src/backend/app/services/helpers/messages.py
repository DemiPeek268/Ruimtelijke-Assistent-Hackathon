from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def to_langchain_history(messages: list[dict]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        else:
            out.append(SystemMessage(content=content))
    return out
