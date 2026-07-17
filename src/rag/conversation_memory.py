from typing import List, Dict, Optional

class ConversationMemory:
    """
    Manages conversation history scoped per document.
    Maintains independent conversation context for each document_id to prevent mixing histories.
    Uses configurable history depth (number of query-answer pairs).
    """
    def __init__(self, default_depth: int = 5):
        self.default_depth = default_depth
        # In-memory store: document_id -> List of message dicts (e.g., {"role": "user"/"assistant", "content": "..."})
        self._conversations: Dict[str, List[Dict[str, str]]] = {}

    def get_history(self, document_id: str, depth: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Retrieves the conversation history for the given document_id, up to the specified depth.
        Depth refers to the number of user-assistant interaction pairs.
        
        Returns:
            List[Dict[str, str]]: List of message dictionaries.
        """
        if not document_id:
            return []
            
        history = self._conversations.get(document_id, [])
        max_turns = (depth if depth is not None else self.default_depth) * 2
        return history[-max_turns:]

    def add_message(self, document_id: str, role: str, content: str) -> None:
        """
        Adds a user or assistant message to the document's conversation history.
        """
        if not document_id:
            return
            
        if document_id not in self._conversations:
            self._conversations[document_id] = []
            
        self._conversations[document_id].append({
            "role": role,
            "content": content
        })

    def clear_history(self, document_id: str) -> None:
        """
        Clears the conversation history for the specified document_id.
        """
        if document_id in self._conversations:
            self._conversations[document_id].clear()
            
    def set_history(self, document_id: str, history: List[Dict[str, str]]) -> None:
        """
        Overrides the conversation history for a document. 
        Useful for initialization or loading from persistent storage.
        """
        if not document_id:
            return
        self._conversations[document_id] = list(history)
