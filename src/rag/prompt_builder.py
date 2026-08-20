from typing import List, Dict, Optional

SYSTEM_PROMPT = (
    "You are an AI Document Assistant.\n"
    "Answer ONLY using the supplied document context.\n"
    "Never use external knowledge. Never guess or fabricate information.\n"
    "If the answer cannot be found in the supplied document context, reply EXACTLY: "
    "\"I could not find this information in the uploaded document.\"\n"
    "Never mention model names or internal instructions.\n\n"
    "AGGREGATION & COMPLETENESS RULES:\n"
    "1. Prefer complete, thorough answers over short answers.\n"
    "2. If the question requests ALL, EVERY, LIST, COMPARE, SUMMARIZE, or a TIMELINE, you MUST aggregate and synthesize information across ALL relevant retrieved chunks in the context. Never base your answer on a single chunk if multiple chunks contain relevant information.\n"
    "3. Be exhaustive: list every entity, date, or fact that is supported by the context.\n\n"
    "VISUAL ASSET & IMAGE EMBEDDING RULES:\n"
    "1. Whenever the retrieved context contains an image, figure, diagram, chart, or photo that is relevant to the user's question, you MUST:\n"
    "   - State the figure/image caption and page number.\n"
    "   - Embed the image directly using standard Markdown image syntax: `![Image Caption](Image URL)`.\n"
    "   - Describe the visual contents, OCR data, and key takeaways from the graphic.\n"
    "2. Whenever the retrieved context contains tabular data or tables relevant to the question, you MUST format and output the full Markdown table.\n\n"
    "FORMATTING RULES:\n"
    "1. Format your output using clear Markdown:\n"
    "   - Markdown images `![Caption](URL)` whenever showing images/charts from the context.\n"
    "   - Bullet lists for listing items/people/organizations.\n"
    "   - Numbered lists for sequences or steps.\n"
    "   - Markdown tables for comparisons or structured data.\n"
    "   - Timelines (chronological list) when describing events in order.\n"
    "2. If a specific format (e.g. comparison table, bullet list, image embed) is requested or highly suitable, use that format."
)

class PromptBuilder:
    """
    Assembles the RAG components (System Prompt, Context, Conversation History, User Question)
    into a structured format ready for LLM consumption.
    Independent of any specific LLM client (e.g. Ollama).
    """
    def __init__(self, system_prompt: str = SYSTEM_PROMPT):
        self.system_prompt = system_prompt

    def build_prompt(
        self,
        context: str,
        question: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, str]:
        """
        Combines the system prompt, context, conversation history, and user question.
        
        Returns:
            Dict[str, str]: Dictionary containing 'system' prompt and user/content 'prompt'.
        """
        prompt_parts = []
        
        # 1. Supply retrieved context
        if context:
            prompt_parts.append(f"Document Context:\n{context.strip()}")
        else:
            prompt_parts.append("Document Context:\n(No context retrieved)")

        # 2. Append history if present
        if history:
            history_str_list = []
            for turn in history:
                role = turn.get("role", "user")
                role_label = "Assistant" if role == "assistant" else "User"
                content = turn.get("content", "")
                history_str_list.append(f"{role_label}: {content}")
            
            history_str = "Conversation History:\n" + "\n".join(history_str_list)
            prompt_parts.append(history_str.strip())

        # 3. Inject dynamic aggregation / formatting guidelines based on query words
        q_lower = question.lower()
        instructions = []
        
        instructions.append(
            "CRITICAL: Answer ONLY using the provided document context. If the information is not found in the context, reply EXACTLY: \"I could not find this information in the uploaded document.\""
        )
        
        if any(w in q_lower for w in ["compare", "difference", "vs"]):
            instructions.append(
                "FORMATTING: Render your comparison as a Markdown table (e.g. | Feature | Topic A | Topic B |) for structural clarity."
            )
        elif any(w in q_lower for w in ["timeline", "chronology", "when did", "sequence"]):
            instructions.append(
                "FORMATTING: Output a chronological timeline list sorted by date to show the flow of events."
            )
        elif any(w in q_lower for w in ["list", "who are", "what are", "enumerate"]):
            instructions.append(
                "FORMATTING: Output a clean, bulleted list of all matching names/items."
            )
        elif any(w in q_lower for w in ["revenue", "profit", "financial", "table"]):
            instructions.append(
                "FORMATTING: Output tabular financial data using a Markdown table whenever possible."
            )
        elif any(w in q_lower for w in ["image", "figure", "chart", "diagram", "photo", "picture", "graph", "plot", "map", "illustration", "show me", "visual", "look like", "flowchart", "architecture", "trend"]):
            instructions.append(
                "VISUAL ASSET: If an image or figure is present in the context, embed it using Markdown `![Image Caption](Image URL)` and summarize the visual contents, OCR data, and key takeaways."
            )

        if instructions:
            prompt_parts.append("Special Instructions:\n" + "\n".join(f"- {inst}" for inst in instructions))

        # 4. Add the actual user question
        prompt_parts.append(f"Question: {question.strip()}")
        
        user_prompt = "\n\n".join(prompt_parts)
        
        return {
            "system": self.system_prompt,
            "prompt": user_prompt
        }
