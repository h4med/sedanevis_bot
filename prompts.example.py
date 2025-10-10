TRANSCRIBER_PROMPT = """
<YOUR_PROMPT_HERE>
"""

TRANSCRIBER_SRT_PROMPT = """
<YOUR_PROMPT_HERE>
"""

SUMMARY_SHORT = """
<YOUR_PROMPT_HERE>
{text}
"""

EXTRACT_POINTS = """
<YOUR_PROMPT_HERE>
{text}
"""

EXTRACT_MOM = """
<YOUR_PROMPT_HERE>
{text}
"""

ACTIONS_PROMPT_MAPPING = {
    'summary_short': SUMMARY_SHORT,
    'extract_points': EXTRACT_POINTS,
    'extract_mom': EXTRACT_MOM,
    'text_to_speech': 'TTS_PLACEHOLDER'
}

ACTIONS_MAX_TOKENS_MAPPING = {
    'summary_short': 1024,
    'extract_points': 16384,
    'extract_mom': 2048
    # TTS cost is calculated differently, so no entry is needed here    
}