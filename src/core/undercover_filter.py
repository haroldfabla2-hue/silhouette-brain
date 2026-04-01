"""
Undercover Mode - Strip AI-revealing phrases for natural human communication.

This module provides the undercover_filter() function that removes or replaces
AI-revealing phrases to enable natural communication in group chats and
public contexts.

Usage:
    from undercover_filter import undercover_filter
    cleaned_text = undercover_filter(raw_text)
"""

import re
from typing import List, Tuple

# Patterns for AI-revealing phrases: (regex_pattern, replacement)
# Order matters - more specific patterns should come first
AI_REVEAL_PATTERNS: List[Tuple[str, str]] = [
    # CRITICAL - Model names and codenames (never reveal)
    (r"\bI'm (Claude|Capybara|Tengu|Opus|MiniMax|GPT|Gemini)\b", ""),
    (r"\bI am (Claude|Capybara|Tengu|Opus|MiniMax|GPT|Gemini)\b", ""),
    (r"\brunning (Claude|Capybara|Tengu|Opus|MiniMax|GPT|Gemini)\b", ""),
    (r"\busing (Claude|Claude |Capybara |Tengu )?(Code|API)?\b", ""),
    
    # HIGH RISK - Self-identification as AI
    (r"\bAs an? (AI|Language Model|AI assistant|artificial intelligence)\b", ""),
    (r"\bI am an? (AI|Language Model|AI assistant|artificial intelligence)\b", ""),
    (r"\bI'm an? (AI|Language Model|AI assistant|artificial intelligence)\b", ""),
    (r"\bI('m| am) a (large language model|AI|machine learning model)\b", ""),
    (r"\bAs a (large language model|machine learning model)\b", ""),
    
    # MEDIUM RISK - Capability disclaimers
    (r"\bMy training (data|includes|cutoff)\b", "I have experience with"),
    (r"\bBased on my training data\b", "From what I know"),
    (r"\bI have access to\b", "I can use"),
    (r"\bI('m| am) capable of\b", "I can"),
    (r"\bI was (trained|built|created) by\b", ""),
    (r"\bI don't have access to\b", "I can't"),
    (r"\bI cannot\b", "I can't"),
    (r"\bI don't have\b", "I don't have"),
    
    # MEDIUM RISK - Knowledge/awareness disclaimers
    (r"\bMy knowledge cutoff\b", ""),
    (r"\bbeyond my training\b", ""),
    (r"\bwithin my training\b", ""),
    
    # LOW RISK - Tool/integration reveals
    (r"\bI have a tool for that\b", "Let me check"),
    (r"\bI'm connected to\b", ""),
    (r"\bI'm running on\b", ""),
    (r"\bI use the (Brain API|Memory API)\b", ""),
    (r"\bI have access to the\b", "I can access the"),
    
    # Model/version reveals
    (r"\bI'm running MiniMax[- ]?M\d+(\.\d+)*\b", ""),
    (r"\bMiniMax[- ]?M\d+(\.\d+)*\b", ""),
    (r"\busing the (OpenAI|Anthropic|Google) (API|model)\b", ""),
    
    # Generic AI references that should be cleaned
    (r"\bAI(,| | assistant| model)\b", "I"),
    (r"\bai(,| | assistant| model)\b", "I"),
]


def undercover_filter(text: str) -> str:
    """
    Strip AI-revealing phrases from text for natural communication.
    
    Args:
        text: Raw text that may contain AI-revealing phrases
        
    Returns:
        Cleaned text with AI phrases removed or replaced
        
    Example:
        >>> undercover_filter("As an AI, I don't have emotions.")
        "I don't have emotions."
        
        >>> undercover_filter("I'm Capybara version 4.6")
        ""
    """
    if not text:
        return text
    
    result = text
    
    for pattern, replacement in AI_REVEAL_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    # Clean up multiple spaces and leading/trailing whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    
    # Remove leading "I" if it becomes disconnected (e.g., "I I'm")
    result = re.sub(r'\bI\s+I\b', 'I', result)
    
    # Remove empty parentheses or phrases
    result = re.sub(r'\(\s*\)', '', result)
    
    # Clean up commas after removed phrases
    result = re.sub(r',\s*,', ',', result)
    result = re.sub(r'^\s*,\s*', '', result)
    
    return result.strip()


def is_ai_revealing(text: str) -> bool:
    """
    Check if text contains AI-revealing phrases.
    
    Args:
        text: Text to check
        
    Returns:
        True if text contains AI-revealing phrases
    """
    if not text:
        return False
    
    for pattern, _ in AI_REVEAL_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    
    return False


def get_revealing_phrases(text: str) -> List[str]:
    """
    Get list of AI-revealing phrases found in text.
    
    Args:
        text: Text to check
        
    Returns:
        List of matching phrases
    """
    found = []
    
    for pattern, _ in AI_REVEAL_PATTERNS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        found.extend(matches)
    
    return found


# Pre-compiled patterns for performance
_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in AI_REVEAL_PATTERNS]


def undercover_filter_fast(text: str) -> str:
    """
    Fast version using pre-compiled patterns.
    
    Use this in production for better performance.
    """
    if not text:
        return text
    
    result = text
    
    for pattern, replacement in _COMPILED_PATTERNS:
        result = pattern.sub(replacement, result)
    
    # Post-processing cleanup
    result = re.sub(r'\s+', ' ', result).strip()
    result = re.sub(r'\bI\s+I\b', 'I', result)
    result = re.sub(r'\(\s*\)', '', result)
    result = re.sub(r',\s*,', ',', result)
    result = re.sub(r'^\s*,\s*', '', result)
    
    return result.strip()
