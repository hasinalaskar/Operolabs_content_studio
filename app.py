import streamlit as st
from pathlib import Path
import os
import base64
import json
import requests
from dotenv import load_dotenv
import sys
import re
import io
import zipfile
import subprocess
import shutil

# Use the EXACT same Flow engine as the working standalone Flow Image Studio.
# The original Flow files are not modified.
FLOW_ENGINE_DIR = Path(r"C:\Users\hasin\OneDrive\Desktop\Flow Image generation")
FLOW_OUTPUT_FOLDER = Path(r"C:\Users\hasin\OperoLabs-Content-Studio\generated_images")
PROJECTS_ROOT = FLOW_OUTPUT_FOLDER


def safe_name(name, fallback="Untitled"):
    """Return a Windows-safe name for projects and output folders."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', str(name)).strip().rstrip('.')
    return cleaned[:100] or fallback


def safe_project_name(name):
    return safe_name(name, "Untitled Project")


def safe_folder_name(name):
    return safe_name(name, "Untitled Project")


def project_folder(project_name=None, folder_name=None):
    folder = folder_name or st.session_state.get("project_folder_name", "")
    if not folder and project_name:
        folder = project_name
    return PROJECTS_ROOT / safe_folder_name(folder)


def project_file(project_name=None, folder_name=None):
    return project_folder(project_name, folder_name) / 'project.json'


def save_project_state(project_name=None):
    """Persist the complete current workflow state for the active project."""
    project_name = (project_name or st.session_state.get('project_name', '')).strip()
    folder_name = (st.session_state.get('project_folder_name') or project_name).strip()
    if not project_name:
        return False

    folder = project_folder(project_name, folder_name)
    folder.mkdir(parents=True, exist_ok=True)

    # Keep the editable Script workspace synchronized with the saved state.
    if 'script_workspace' in st.session_state:
        st.session_state.script_text = st.session_state.script_workspace

    state = {
        'project_name': project_name,
        'folder_name': safe_folder_name(folder_name),
        'script_text': st.session_state.get('script_text', ''),
        'voice_transcript': st.session_state.get('voice_transcript', ''),
        'visual_segments': st.session_state.get('visual_segments', []),
        'visual_prompts': st.session_state.get('visual_prompts', []),
        'master_visual_prompt': st.session_state.get('master_visual_prompt', ''),
        'continuity_instructions': st.session_state.get('continuity_instructions', ''),
        'negative_prompt': st.session_state.get('negative_prompt', ''),
    }

    (folder / 'project.json').write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    if state['script_text']:
        (folder / 'script.txt').write_text(state['script_text'], encoding='utf-8')
    if state['voice_transcript']:
        (folder / 'transcription.txt').write_text(state['voice_transcript'], encoding='utf-8')
    if state['visual_segments']:
        (folder / 'visual_segments.json').write_text(
            json.dumps(state['visual_segments'], indent=2, ensure_ascii=False), encoding='utf-8'
        )
    if state['visual_prompts']:
        (folder / 'visual_prompts.json').write_text(
            json.dumps(state['visual_prompts'], indent=2, ensure_ascii=False), encoding='utf-8'
        )
    return True


def load_project_state(folder_name):
    """Load a saved project from its output folder."""
    path = project_file(folder_name=folder_name)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding='utf-8'))
    saved_folder = data.get('folder_name', folder_name)
    st.session_state.project_name = data.get('project_name', folder_name)
    st.session_state.project_folder_name = saved_folder
    st.session_state.script_text = data.get('script_text', '')
    st.session_state.voice_transcript = data.get('voice_transcript', '')
    st.session_state.visual_segments = data.get('visual_segments', [])
    st.session_state.visual_prompts = data.get('visual_prompts', [])
    st.session_state.master_visual_prompt = data.get('master_visual_prompt', '')
    st.session_state.continuity_instructions = data.get('continuity_instructions', '')
    st.session_state.negative_prompt = data.get('negative_prompt', '')
    st.session_state.generated_image_files = project_image_files(
        saved_folder, st.session_state.visual_prompts
    )
    # Reset editable widget values so reopening visibly restores the saved project.
    st.session_state.script_workspace = st.session_state.script_text
    st.session_state.voice_transcript_workspace = st.session_state.voice_transcript
    return True


def image_path_for_prompt(folder, item):
    return folder / f"{str(item['start']).replace(':', '.')}.jpg"


def project_image_files(folder_name, visual_prompts):
    folder = project_folder(folder_name=folder_name)
    files = []
    for item in visual_prompts:
        path = image_path_for_prompt(folder, item)
        if path.exists():
            files.append(path)
    return files



def image_generation_status_path(folder_name):
    """Return the shared status-file path used by the independent image worker."""
    return project_folder(folder_name=folder_name) / ".image_generation_status.json"


def read_image_generation_status(folder_name):
    """Read the worker status written by image_generation_worker.py."""
    path = image_generation_status_path(folder_name)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_image_generation_status(folder_name, data):
    """Atomically write the worker status so Streamlit never reads a partial JSON file."""
    path = image_generation_status_path(folder_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)

def reset_project_session():
    """Clear all workflow data when switching to a different project."""
    st.session_state.script_text = ""
    st.session_state.script_workspace = ""
    st.session_state.voice_transcript = ""
    st.session_state.voice_transcript_workspace = ""
    st.session_state.visual_segments = []
    st.session_state.visual_prompts = []
    st.session_state.master_visual_prompt = ""
    st.session_state.continuity_instructions = ""
    st.session_state.negative_prompt = ""
    st.session_state.generated_image_files = []


def sync_stage_widgets_to_project():
    """Copy current editable stage widgets into the project's persistent state."""
    if st.session_state.get("script_workspace") is not None:
        st.session_state.script_text = st.session_state.script_workspace

    if st.session_state.get("voice_transcript_workspace") is not None:
        st.session_state.voice_transcript = st.session_state.voice_transcript_workspace

    # Visual planner text areas use the same session-state keys as the project state.
    if st.session_state.get("visual_prompts"):
        for item in st.session_state.visual_prompts:
            key = f"visual_prompt_{item['start']}"
            if key in st.session_state:
                item["prompt"] = st.session_state[key]


def autosave_active_project():
    """Persist the active project's current stage data on normal app navigation/reruns."""
    if not st.session_state.get("project_name", "").strip():
        return
    sync_stage_widgets_to_project()
    save_project_state()


if str(FLOW_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(FLOW_ENGINE_DIR))

from flow_engine import generate_images
import re

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="OperoLabs | AI Content Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# BRAND COLORS
# =========================================================

NAVY = "#0B1020"
PANEL = "#12192A"
PANEL_2 = "#171F33"
GOLD = "#D4AF5A"
IVORY = "#F4F0E6"
MUTED = "#9DA3B0"
BORDER = "#2A3245"

# =========================================================
# OPENROUTER CONFIGURATION
# =========================================================
# Reuse the existing OperoVoice .env so we do not create
# another API-key setup for this frontend.

OPEROVOICE_ENV = Path(r"C:\Users\hasin\OperoVoice\.env")
OPEROVOICE_DATA_DIR = OPEROVOICE_ENV.parent
TRANSCRIPTION_JSON_PATH = OPEROVOICE_DATA_DIR / "transcription.json"
VISUAL_SEGMENTS_JSON_PATH = OPEROVOICE_DATA_DIR / "visual_segments.json"

load_dotenv(OPEROVOICE_ENV)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SCRIPT_MODEL = "openai/gpt-4o-mini"
TRANSCRIPTION_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
TRANSCRIPTION_MODEL = "openai/whisper-large-v3"


# =========================================================
# CUSTOM CSS
# =========================================================
# CSS is contained in this single styling block.
# No HTML is used for the visible page content.

st.markdown(
    f"""
    <style>

    /* -----------------------------------------------------
       REMOVE STREAMLIT'S TOP BAR / EMPTY WHITE SPACE
       ----------------------------------------------------- */

    [data-testid="stHeader"] {{
        display: none !important;
    }}

    [data-testid="stToolbar"] {{
        display: none !important;
    }}

    .stAppViewContainer {{
        padding-top: 0 !important;
    }}

    .main .block-container {{
        padding-top: 3rem !important;
        padding-bottom: 2rem !important;
    }}

    /* -----------------------------------------------------
       MAIN APP
       ----------------------------------------------------- */

    .stApp {{
        background-color: {NAVY};
        color: {IVORY};
    }}

    /* -----------------------------------------------------
       SIDEBAR
       ----------------------------------------------------- */

    [data-testid="stSidebar"] {{
        background-color: #080D19;
        border-right: 1px solid {BORDER};
    }}

    [data-testid="stSidebar"] * {{
        color: {IVORY};
    }}

    /* Keep logo centered and fully visible */
    [data-testid="stSidebar"] [data-testid="stImage"] {{
        display: flex;
        justify-content: center;
        width: 100%;
    }}

    [data-testid="stSidebar"] [data-testid="stImage"] img {{
        display: block;
        width: 150px !important;
        max-width: 150px !important;
        height: auto !important;
        object-fit: contain !important;
        background-color: {IVORY};
        border-radius: 12px;
        padding: 10px 14px;
        box-sizing: border-box;
    }}

    /* -----------------------------------------------------
       HIDE DEFAULT STREAMLIT MENU / FOOTER
       ----------------------------------------------------- */

    #MainMenu {{
        visibility: hidden;
    }}

    footer {{
        visibility: hidden;
    }}

    /* -----------------------------------------------------
       MAIN TITLE
       ----------------------------------------------------- */

    h1 {{
        color: {GOLD} !important;
        font-family: Georgia, serif !important;
        font-size: 42px !important;
        font-weight: 600 !important;
        letter-spacing: 1px !important;
        margin-bottom: 4px !important;
    }}

    h2, h3 {{
        color: {IVORY} !important;
        font-family: Georgia, serif !important;
    }}

    /* Small uppercase descriptive text */
    .studio-subtitle {{
        color: {MUTED};
        font-size: 13px;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 28px;
    }}

    .section-label {{
        color: {GOLD};
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 7px;
    }}

    /* -----------------------------------------------------
       DASHBOARD CARDS
       ----------------------------------------------------- */

    .workflow-card {{
        background-color: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 20px;
        min-height: 135px;
    }}

    .workflow-number {{
        color: {GOLD};
        font-size: 12px;
        letter-spacing: 2px;
        font-weight: 600;
    }}

    .workflow-title {{
        color: {IVORY};
        font-family: Georgia, serif;
        font-size: 23px;
        margin-top: 8px;
    }}

    .workflow-text {{
        color: {MUTED};
        font-size: 13px;
        line-height: 1.5;
        margin-top: 7px;
    }}

    /* -----------------------------------------------------
       FORM CONTROLS
       ----------------------------------------------------- */

    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    div[data-baseweb="select"] > div {{
        background-color: {PANEL};
        border-color: {BORDER};
    }}

    input,
    textarea {{
        color: #1B2230 !important;
        -webkit-text-fill-color: #1B2230 !important;
        caret-color: #1B2230 !important;
    }}

    input::placeholder,
    textarea::placeholder {{
        color: #6F7785 !important;
        -webkit-text-fill-color: #6F7785 !important;
        opacity: 1 !important;
    }}

    div[data-baseweb="select"] * {{
        color: #1B2230 !important;
    }}

    label {{
        color: {IVORY} !important;
    }}

    /* -----------------------------------------------------
       BUTTONS
       ----------------------------------------------------- */

    .stButton > button {{
        border-radius: 8px;
        border: 1px solid {GOLD};
        background-color: {PANEL};
        color: {GOLD};
        min-height: 42px;
        font-weight: 500;
    }}

    .stButton > button:hover {{
        background-color: {PANEL_2};
        color: white;
        border-color: {GOLD};
    }}

    /* DOWNLOAD BUTTONS */
    [data-testid="stDownloadButton"] button {{
        color: #1B2230 !important;
        -webkit-text-fill-color: #1B2230 !important;
        background-color: #FFFFFF !important;
        border: 1px solid {BORDER} !important;
        font-weight: 600 !important;
    }}

    [data-testid="stDownloadButton"] button:hover {{
        color: #1B2230 !important;
        -webkit-text-fill-color: #1B2230 !important;
        background-color: #F2F3F5 !important;
        border-color: {GOLD} !important;
    }}

    /* -----------------------------------------------------
       SIDEBAR NAVIGATION
       ----------------------------------------------------- */

    [data-testid="stSidebar"] .stRadio label {{
        font-size: 14px;
    }}

    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# SCRIPT GENERATION
# =========================================================

def generate_script(
    topic,
    content_form,
    language,
    length,
    tone,
    audience,
    structure,
    style_instructions,
):
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY was not found in the OperoVoice .env file."
        )

    length_guidance = {
        "3–4 minutes": "HARD TARGET: 450–600 words",
        "5–6 minutes": "HARD TARGET: 750–900 words",
        "8–10 minutes": "HARD TARGET: 1000–1200 words",
        "10–15 minutes": "HARD TARGET: 1500–1800 words",
        "Custom": "follow the user's custom word-count requirement exactly",
    }.get(length, "follow the requested length naturally")

    prompt = f"""
You are an expert content scriptwriter.

Create a complete narration script using the user's specifications below.

TOPIC / TITLE:
{topic}

CONTENT FORM:
{content_form}

LANGUAGE:
{language}

TARGET LENGTH:
{length} — {length_guidance}

LENGTH IS A HARD REQUIREMENT:
- The selected length must produce a script within the stated word-count range.
- Do NOT treat the word count as a suggestion.
- Before finishing, silently check the approximate word count.
- If the script is below the minimum, continue writing until it reaches the minimum.
- Do not shorten the script just to reach the ending.
- The 5–6 minute and 8–10 minute options MUST produce noticeably different script lengths.

TONE:
{tone}

TARGET AUDIENCE:
{audience}

SCRIPT STRUCTURE / SPECIAL REQUIREMENTS:
{structure if structure.strip() else "No additional structure specified."}

CHANNEL / SCRIPT STYLE INSTRUCTIONS:
{style_instructions if style_instructions.strip() else "No additional channel style specified."}

IMPORTANT:
- Follow the requested language exactly.
- Follow the requested content form rather than imposing a documentary style.
- Follow the user's tone and audience requirements.
- Treat EVERY instruction written in the two instruction boxes as an actual requirement for the script.
- Interpret natural-language instructions intelligently. The user does not need to use technical prompt-writing terminology.
- Apply instructions about first person, second person, third person, narrator, characters, personal experience, storytelling perspective, tone, pacing, structure, opening, ending, emotional treatment, or any other creative requirement throughout the script.
- If the user asks for a specific narrator, character, point of view, or storytelling setup, follow it consistently.
- Do not replace the user's requested style or structure with a generic documentary style.
- When multiple user instructions are compatible, follow all of them together.
- For factual, historical, scientific, cultural, or biographical content, prioritize well-researched and accurate information. Cross-check important claims against established knowledge, distinguish uncertain or disputed claims, and never invent dates, people, events, quotations, or facts simply to make the story more dramatic.
- Make the narration natural and suitable for voice-over.
- Keep the narrative moving continuously toward the final conclusion.
- Do NOT write an apparent conclusion, final reflection, summary, or thought-provoking question before the actual end of the script.
- If the script still needs more words, develop the history, context, characters, events, or other relevant material BEFORE the conclusion.
- The final reflection or thought-provoking question must be the final spoken material.
- Never conclude the story and then reopen it with additional story material.

OUTPUT RULES — VERY IMPORTANT:
- Return ONLY the final spoken narration.
- Do NOT include scene directions or visual descriptions.
- Do NOT include camera directions or production directions.
- Do NOT use labels such as "Narrator:" or character names.
- Do NOT include brackets such as [Opening Scene], [Cut to], [Transition], [Fade out], or similar.
- Do NOT include music, sound effects, editing notes, image prompts, or shot descriptions.
- Do NOT add a title, heading, introduction, explanation, or conclusion outside the narration itself.
- The result must be ready to paste directly into a text-to-speech tool.
- Write only the words that should be spoken aloud.
"""

    word_targets = {
        "3–4 minutes": (450, 600),
        "5–6 minutes": (750, 900),
        "8–10 minutes": (1000, 1200),
        "10–15 minutes": (1500, 1800),
    }
    minimum_words, maximum_words = word_targets.get(length, (0, 10**9))

    system_message = {
        "role": "system",
        "content": (
            "You are the scriptwriting engine inside a professional content "
            "creation application. User instructions are actual requirements, "
            "not optional suggestions. Interpret simple natural language "
            "intelligently and apply every applicable instruction throughout "
            "the script. This includes point of view, narrator, characters, "
            "personal experience, tone, pacing, structure, opening, ending, "
            "and any other creative requirement. Keep the narrative continuous and ensure that any conclusion, final reflection, or thought-provoking question appears only at the true end of the script. Do not conclude and then reopen the story. Do not replace a user's "
            "specific request with a generic writing style."
        ),
    }

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": SCRIPT_MODEL,
            "messages": [system_message, {"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 4000,
        },
        timeout=180,
    )

    if response.status_code != 200:
        try:
            error_detail = response.json()
        except Exception:
            error_detail = response.text
        raise RuntimeError(
            f"OpenRouter returned HTTP {response.status_code}: {error_detail}"
        )

    data = response.json()
    try:
        script = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Unexpected OpenRouter response: {data}")

    word_count = len(script.split())

    # Shared refusal markers used by the expansion/rewrite logic below.
    # Keep these outside repair_narrative_flow so every branch can access them.
    refusal_markers = [
        "i'm sorry, but i can't",
        "i’m sorry, but i can’t",
        "i can't continue",
        "i can’t continue",
        "without seeing the previous",
        "if you provide the previous",
    ]

    def has_premature_ending(draft):
        """Detect a conclusion-like passage followed by substantial narration."""
        conclusion_markers = [
            "as we reflect on",
            "as we look back",
            "in conclusion",
            "ultimately,",
            "ultimately ",
            "one cannot help but wonder",
            "what stories do our",
            "what does this tell us",
            "as we savor",
            "as we consider this journey",
            "as this journey comes to an end",
            "perhaps the question is",
        ]
        paragraphs = [p.strip() for p in draft.split("\n\n") if p.strip()]
        if len(paragraphs) < 3:
            return False

        total_words = len(draft.split())
        for i, paragraph in enumerate(paragraphs[:-1]):
            lower = paragraph.lower()
            if any(marker in lower for marker in conclusion_markers):
                words_after = sum(len(p.split()) for p in paragraphs[i + 1:])
                # Only flag it when a meaningful amount of narration follows.
                if words_after >= 80 and i < len(paragraphs) - 2:
                    return True
        return False

    def repair_narrative_flow(draft):
        """Repair an early conclusion only when one is actually detected."""
        if not has_premature_ending(draft):
            return draft

        repair_prompt = f"""
The script below has a structural problem: it reaches a conclusion or final
reflection too early and then continues with additional story material.

Rewrite the COMPLETE script so it becomes one continuous narrative.

CRITICAL:
- Keep all useful factual content, story details, characters, perspective,
  tone, and user-requested structure.
- Move any conclusion, final reflection, summary, or thought-provoking question
  that appears too early to the TRUE END.
- Material that currently appears after the premature conclusion must remain
  part of the story and must come BEFORE the final conclusion.
- Do not delete substantial content merely to hide the problem.
- There must be ONE clear ending, and it must be the final spoken material.
- If there is a thought-provoking question, it must be the final spoken line or
  part of the final paragraph.
- Do not introduce a new ending halfway through the script.
- Keep the script within approximately the same word-count range.
- Return ONLY the complete spoken narration.

COMPLETE SCRIPT:
{draft}
"""

        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": SCRIPT_MODEL,
                "messages": [
                    system_message,
                    {"role": "user", "content": repair_prompt},
                ],
                "temperature": 0.25,
                "max_tokens": 4000,
            },
            timeout=180,
        )

        if response.status_code != 200:
            return draft

        try:
            repaired = response.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return draft

        if not repaired:
            return draft

        if any(marker in repaired.lower() for marker in refusal_markers):
            return draft

        return repaired

    if minimum_words <= word_count <= maximum_words:
        return repair_narrative_flow(script)

    # If the first response is short, rewrite the COMPLETE script instead of
    # appending a continuation. This prevents a model-generated ending from
    # being followed by a new story section.
    if word_count < minimum_words:
        for _ in range(4):
            word_count = len(script.split())
            if word_count >= minimum_words:
                return repair_narrative_flow(script)

            words_needed = minimum_words - word_count

            expansion_prompt = f"""
Rewrite and expand the COMPLETE script below so that it reaches the required
length of {minimum_words}–{maximum_words} words.

The current script contains approximately {word_count} words. Add enough
relevant material to reach the target, while keeping the story coherent.

CRITICAL: 
- Return the COMPLETE revised script, NOT a continuation.
- Do not append a new section after the existing ending.
- Expand the historical context, events, details, or narrative development
  BEFORE the final conclusion.
- Keep ONE continuous narrative progression from beginning to end.
- There must be ONE clear ending only.
- The final reflection or thought-provoking question must be the FINAL spoken
  material in the complete script.
- Never repeat the ending or thought-provoking question.
- Do not introduce a new story, character, or plot after the conclusion.
- Preserve the requested point of view, narrator, characters, tone, structure,
  style, and factual requirements.
- Do not summarize the existing script instead of expanding it.
- Return ONLY the complete spoken narration.
- Do not include headings, labels, notes, explanations, or commentary.

COMPLETE CURRENT SCRIPT:
{script}
"""

            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": SCRIPT_MODEL,
                    "messages": [
                        system_message,
                        {"role": "user", "content": expansion_prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 4000,
                },
                timeout=180,
            )

            if response.status_code != 200:
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                raise RuntimeError(
                    f"OpenRouter returned HTTP {response.status_code}: {error_detail}"
                )

            data = response.json()
            try:
                revised = data["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError):
                raise RuntimeError(f"Unexpected OpenRouter response: {data}")

            if not revised:
                break

            lowered = revised.lower()
            if any(marker in lowered for marker in refusal_markers):
                break

            # Replace the whole draft. Never append a continuation.
            script = revised

            if minimum_words <= len(script.split()) <= maximum_words:
                return repair_narrative_flow(script)

        # If the model still did not reach the minimum, return the last
        # complete rewrite rather than appending anything after its ending.
        return repair_narrative_flow(script)

    # If the first response is above the maximum, make one targeted rewrite.
    instruction = f"""
Rewrite the complete script below into the required range of
{minimum_words}–{maximum_words} words.

Preserve the user's requested facts, narrative perspective, narrator,
characters, tone, structure, style, and intended ending. Remove repetition and
unnecessary wording rather than changing the requested creative approach.
Make sure the narrative progresses continuously toward one final conclusion.
If the current draft concludes and then continues, restructure that material so
the conclusion appears only once, at the true end. The final reflection or
thought-provoking question must be the final spoken material.

Return ONLY the complete revised spoken narration. Do not include headings,
labels, notes, or commentary.

COMPLETE CURRENT SCRIPT:
{script}
"""

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": SCRIPT_MODEL,
            "messages": [
                system_message,
                {"role": "user", "content": instruction},
            ],
            "temperature": 0.4,
            "max_tokens": 4000,
        },
        timeout=180,
    )

    if response.status_code != 200:
        try:
            error_detail = response.json()
        except Exception:
            error_detail = response.text
        raise RuntimeError(
            f"OpenRouter returned HTTP {response.status_code}: {error_detail}"
        )

    data = response.json()
    try:
        revised = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Unexpected OpenRouter response: {data}")

    if not revised:
        return repair_narrative_flow(script)

    return repair_narrative_flow(revised)


# =========================================================
# VOICE TRANSCRIPTION
# =========================================================

def transcribe_audio(audio_bytes, filename):
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY was not found in the OperoVoice .env file."
        )

    encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

    # OpenRouter's current transcription API expects the audio inside
    # an input_audio object: {data: <base64>, format: <extension>}.
    # Do not send a data: URL here.
    extension = Path(filename).suffix.lower().lstrip(".")
    supported_formats = {"mp3", "wav", "flac", "m4a", "ogg", "webm", "aac"}
    audio_format = extension if extension in supported_formats else "mp3"

    response = requests.post(
        TRANSCRIPTION_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": TRANSCRIPTION_MODEL,
            "input_audio": {
                "data": encoded_audio,
                "format": audio_format,
            },
            "response_format": "verbose_json",
            "timestamp_granularities": ["word"],
        },
        timeout=300,
    )

    if response.status_code != 200:
        try:
            error_detail = response.json()
        except Exception:
            error_detail = response.text
        raise RuntimeError(
            f"OpenRouter transcription failed (HTTP {response.status_code}): {error_detail}"
        )

    data = response.json()
    words = data.get("words") or []
    text = (data.get("text") or "").strip()

    if not words:
        raise RuntimeError("The transcription did not contain word timestamps.")

    # ---------------------------------------------------------
    # LOCAL TRANSCRIPTION CLEANUP
    # ---------------------------------------------------------
    # This runs AFTER Whisper and BEFORE timestamp segmentation.
    # It does not make another API call and does not alter timestamps.
    # Only very obvious one-word transcription artifacts are removed.
    # We deliberately keep this conservative so genuine narration is not
    # accidentally changed.
    cleaned_words = []
    i = 0
    while i < len(words):
        word = dict(words[i])
        token = str(word.get("word", "")).strip()
        lower = token.lower().strip(".,!?;:")

        # Whisper occasionally inserts a stray standalone "you" immediately
        # before a new sentence. Only remove it when the following word starts
        # a new sentence and there is a clear pause before that following word.
        if (
            lower == "you"
            and i + 1 < len(words)
            and re.match(r"^[A-Z]", str(words[i + 1].get("word", "")).strip())
            and float(words[i + 1].get("start", 0)) - float(word.get("end", 0)) >= 0.25
        ):
            i += 1
            continue

        cleaned_words.append(word)
        i += 1

    words = cleaned_words

    # Rebuild the displayed transcription text from the cleaned word list.
    text = " ".join(str(w.get("word", "")).strip() for w in words).strip()

    # Local cleanup for obvious Whisper artifacts.
    # This does not call the API and does not change timestamps.
    # Example: "you This" -> "This" when a stray standalone word appears
    # immediately before a new sentence.
    cleaned_words = []
    for idx, word in enumerate(words):
        token = str(word.get("word", "")).strip()
        if (
            token.lower() == "you"
            and idx + 1 < len(words)
            and str(words[idx + 1].get("word", "")).strip()
            and str(words[idx + 1].get("word", "")).strip()[0].isupper()
        ):
            continue
        cleaned_words.append(word)
    words = cleaned_words

    # Save the exact transcription returned by OpenRouter so the latest
    # Voice run can be inspected independently of Streamlit session state.
    try:
        TRANSCRIPTION_JSON_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as save_error:
        raise RuntimeError(
            f"Transcription succeeded, but could not save "
            f"{TRANSCRIPTION_JSON_PATH}: {save_error}"
        )

    return text, words


def build_visual_segments(words):
    """Build tight narration segments around a 3.5-second rhythm.

    Timestamp-only change from the working app:
    - target: about 3.5 seconds
    - natural sentence/phrase punctuation is preferred
    - no complete-sentence exception beyond the 3.8-second cap
    - segments do not intentionally extend toward 4.2+ seconds
    """

    TARGET_SECONDS = 3.5
    MIN_SEGMENT = 2.5
    MAX_SEGMENT = 3.8

    def clean(word):
        return str(word.get("word", "")).strip()

    def is_sentence_end(word):
        return bool(re.search(r"[.!?]$", clean(word)))

    def is_phrase_end(word):
        return bool(re.search(r"[,;:]$", clean(word)))

    def duration(selected):
        if not selected:
            return 0.0
        return float(selected[-1]["end"]) - float(selected[0]["start"])

    def make_segment(selected):
        if not selected:
            return None
        return {
            "start": round(float(selected[0]["start"]), 2),
            "end": round(float(selected[-1]["end"]), 2),
            "duration": round(duration(selected), 2),
            "text": " ".join(clean(w) for w in selected),
        }

    segments = []
    i = 0

    while i < len(words):
        start_index = i
        best_natural = None
        best_natural_distance = float("inf")
        best_word = start_index
        best_word_distance = float("inf")

        for j in range(start_index, len(words)):
            d = float(words[j]["end"]) - float(words[start_index]["start"])

            if d > MAX_SEGMENT:
                break

            # Keep track of the closest word boundary to 3.5 seconds.
            distance = abs(d - TARGET_SECONDS)
            if distance < best_word_distance:
                best_word_distance = distance
                best_word = j

            # Prefer a natural punctuation boundary when it is inside the cap.
            if (is_phrase_end(words[j]) or is_sentence_end(words[j])) and d >= MIN_SEGMENT:
                if distance < best_natural_distance:
                    best_natural_distance = distance
                    best_natural = j

        # Prefer punctuation near 3.5s; otherwise use the closest word boundary.
        chosen = best_natural if best_natural is not None else best_word

        # If the remaining narration is shorter than the minimum, keep it intact.
        remaining_words = words[start_index:]
        if remaining_words:
            remaining_duration = duration(remaining_words)
            if remaining_duration <= MAX_SEGMENT:
                chosen = len(words) - 1

        segment = make_segment(words[start_index:chosen + 1])
        if segment:
            segments.append(segment)

        i = chosen + 1

    return segments


# =========================================================
# VISUAL PROMPT GENERATION
# =========================================================

def generate_visual_prompts(segments, master_style, continuity, negative_prompt):
    """Create one scene-specific visual description per narration segment.

    The AI creates ONLY the scene description. The app then locks the user's
    master style, continuity instructions, and negative prompt onto every
    final prompt so they are not paraphrased or lost.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY was not found in the OperoVoice .env file."
        )

    segment_text = "\n\n".join(
        f"SEGMENT {i + 1}\n"
        f"TIMESTAMP: [{int(round(float(s['start'])) // 60)}:{int(round(float(s['start'])) % 60):02d}]\n"
        f"EXACT NARRATION: {s['text']}"
        for i, s in enumerate(segments)
    )

    prompt = f"""Create one highly specific image-scene description for EACH narration segment below.

Your job is ONLY to describe what should be visible in the image for that exact narration segment.
Do not write the final image-generation prompt. The application will add the user's locked style later.

MASTER STYLE (DO NOT USE THIS TO CHANGE THE SCENE MEANING):
{master_style.strip()}

CHARACTER / CONTINUITY:
{continuity.strip() or 'Maintain continuity of recurring people, places, objects, clothing, architecture, and time period when relevant.'}

NEGATIVE PROMPT:
{negative_prompt.strip() or 'No text, captions, logos, watermarks, distorted anatomy, duplicate people, or inconsistent recurring characters.'}

IMPORTANT VISUAL-PLANNING RULES:
1. Create exactly ONE scene description for every segment, in exactly the same order.
2. Read the EXACT NARRATION of each segment carefully before writing its scene.
3. The scene MUST directly visualize that specific narration. Do not use information from another segment.
4. Do NOT repeat a generic scene such as a restaurant, chef, spices, partition, railway, or cooking scene unless the exact narration calls for it.
5. Do NOT invent historical events, people, locations, dates, or actions that are not supported by that segment.
6. For abstract narration, use a clear visual metaphor that still represents the exact meaning of that sentence.
7. Include concrete visual details: subject, action, environment, period/location when supported, composition, lighting, and important objects.
8. Make each scene description detailed enough for Google Flow/image generation.
9. Do not include timestamps, narration, headings, labels, style instructions, negative prompts, or explanations in the scene description.
10. Return exactly {len(segments)} objects.

TIMESTAMPED NARRATION:

{segment_text}

Return this exact JSON structure:
{{
  "scenes": [
    {{"index": 1, "scene": "Specific scene description for segment 1"}},
    {{"index": 2, "scene": "Specific scene description for segment 2"}}
  ]
}}
"""

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": SCRIPT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a visual storyboard planner. Your only task is to translate each "
                        "individual narration segment into a specific visible scene. Follow the "
                        "segment-by-segment mapping exactly. Never substitute a generic scene or "
                        "borrow content from another segment."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "visual_scenes",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "scenes": {
                                "type": "array",
                                "minItems": len(segments),
                                "maxItems": len(segments),
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "index": {"type": "integer"},
                                        "scene": {"type": "string"},
                                    },
                                    "required": ["index", "scene"],
                                },
                            }
                        },
                        "required": ["scenes"],
                    },
                },
            },
        },
        timeout=180,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"OpenRouter visual prompt generation failed (HTTP {response.status_code}): {response.text}"
        )

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    content = str(content).strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"The AI returned invalid visual scene data: {exc}")

    scenes = result.get("scenes") if isinstance(result, dict) else None
    if not isinstance(scenes, list) or len(scenes) != len(segments):
        actual = len(scenes) if isinstance(scenes, list) else 0
        raise RuntimeError(
            f"The AI returned {actual} visual scenes, but {len(segments)} were expected."
        )

    master = master_style.strip().rstrip("., ")
    continuity_text = continuity.strip().rstrip("., ")
    negative = negative_prompt.strip().rstrip("., ")

    final_prompts = []
    for i, item in enumerate(scenes):
        if not isinstance(item, dict):
            raise RuntimeError(f"Visual scene {i + 1} is invalid.")
        if int(item.get("index", -1)) != i + 1:
            raise RuntimeError(f"Visual scene order is incorrect at segment {i + 1}.")

        scene = str(item.get("scene", "")).strip()
        if not scene:
            raise RuntimeError(f"Visual scene {i + 1} is empty.")

        start_seconds = int(round(float(segments[i]["start"])))
        minutes = start_seconds // 60
        seconds = start_seconds % 60

        parts = [scene]
        if master:
            parts.append(master)
        if continuity_text:
            parts.append(continuity_text)
        if negative:
            parts.append(negative)

        final_prompts.append({
            "start": f"{minutes}:{seconds:02d}",
            "prompt": ", ".join(parts).rstrip(". ") + ".",
        })

    return final_prompts


# =========================================================
# SESSION STATE
# =========================================================

if "project_name" not in st.session_state:
    st.session_state.project_name = ""

if "project_folder_name" not in st.session_state:
    st.session_state.project_folder_name = ""

if "generated_image_files" not in st.session_state:
    st.session_state.generated_image_files = []

if "script_text" not in st.session_state:
    st.session_state.script_text = ""

if "script_workspace" not in st.session_state:
    st.session_state.script_workspace = ""

if "voice_transcript_workspace" not in st.session_state:
    st.session_state.voice_transcript_workspace = ""

if "master_visual_prompt" not in st.session_state:
    st.session_state.master_visual_prompt = ""

if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = ""

if "visual_segments" not in st.session_state:
    st.session_state.visual_segments = []

if "visual_prompts" not in st.session_state:
    st.session_state.visual_prompts = []

if "continuity_instructions" not in st.session_state:
    st.session_state.continuity_instructions = ""

if "negative_prompt" not in st.session_state:
    st.session_state.negative_prompt = ""

if "selected_project_folder" not in st.session_state:
    st.session_state.selected_project_folder = ""

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    logo_path = Path("operolabs_logo.png")

    if logo_path.exists():
        st.image(str(logo_path), width=150)

    st.divider()

    st.caption("AI CONTENT STUDIO")

    page = st.radio(
        "Studio Navigation",
        [
            "Dashboard",
            "Script",
            "Voice",
            "Visual Planner",
            "Images",
            "Projects",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    if st.session_state.project_name:
        st.caption("CURRENT PROJECT")
        st.write(st.session_state.project_name)
    else:
        st.caption("NO PROJECT SELECTED")

# Persist the active project whenever the user navigates between stages.
# This makes the project folder the source of truth instead of transient UI state.
if page not in ["Dashboard", "Projects"] and st.session_state.get("project_name", "").strip():
    autosave_active_project()

# =========================================================
# DASHBOARD
# =========================================================

if page == "Dashboard":

    st.title("AI Content Studio")

    st.markdown(
        '<div class="studio-subtitle">FROM IDEA TO FINISHED VISUALS</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-label">PROJECT</div>',
        unsafe_allow_html=True,
    )

    col_project, col_folder = st.columns(2)

    with col_project:
        project = st.text_input(
            "Project name",
            value=st.session_state.project_name,
            placeholder="Example: Haleem — History of a Dish",
        )

    with col_folder:
        folder_name = st.text_input(
            "Output folder name",
            value=st.session_state.project_folder_name,
            placeholder="Example: Haleem_History",
            help="All project files and generated images will be saved inside this folder under generated_images.",
        )

    if st.button("Create Project", type="primary"):
        if not project.strip():
            st.warning("Please enter a project name.")
        elif not folder_name.strip():
            st.warning("Please enter an output folder name.")
        else:
            project_clean = safe_project_name(project)
            folder_clean = safe_folder_name(folder_name)
            folder = project_folder(folder_name=folder_clean)
            if (folder / "project.json").exists():
                st.warning("That output folder already belongs to a project. Choose another folder name.")
            else:
                st.session_state.project_name = project_clean
                st.session_state.project_folder_name = folder_clean
                reset_project_session()
                save_project_state(project_clean)
                st.success(f"Project created: {project_clean}")

    st.write("")

    st.markdown(
        '<div class="section-label">CONTENT WORKFLOW</div>',
        unsafe_allow_html=True,
    )

    st.write("")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
            <div class="workflow-card">
                <div class="workflow-number">01 — SCRIPT</div>
                <div class="workflow-title">Create the Story</div>
                <div class="workflow-text">
                    Define the topic, content form, language,
                    tone, audience and writing preferences.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="workflow-card">
                <div class="workflow-number">02 — VOICE</div>
                <div class="workflow-title">Build the Narration</div>
                <div class="workflow-text">
                    Upload your manually generated Fish Audio
                    narration and create timestamped segments.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    col3, col4 = st.columns(2)

    with col3:
        st.markdown(
            """
            <div class="workflow-card">
                <div class="workflow-number">03 — VISUAL PLANNER</div>
                <div class="workflow-title">Plan the Visuals</div>
                <div class="workflow-text">
                    Combine your master visual style with each
                    timestamped narration segment.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            """
            <div class="workflow-card">
                <div class="workflow-number">04 — IMAGES</div>
                <div class="workflow-title">Generate the Visuals</div>
                <div class="workflow-text">
                    Send approved timestamped prompts to your
                    existing Flow Image Studio.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    st.caption(
        "The four stages will be connected one at a time after "
        "the frontend is finalized."
    )

# =========================================================
# SCRIPT
# =========================================================

elif page == "Script":

    st.title("Script")

    if not st.session_state.get("project_name", "").strip():
        st.warning("Please create or open a project from Dashboard or Projects before using this stage.")
        st.stop()

    st.markdown(
        '<div class="studio-subtitle">CREATE A SCRIPT FOR ANY TYPE OF CONTENT</div>',
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------
    # CONTENT SETUP
    # -----------------------------------------------------

    st.markdown(
        '<div class="section-label">CONTENT SETUP</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        topic = st.text_input(
            "Topic / Title",
            placeholder="What is your video about?",
        )

    with col2:
        language = st.selectbox(
            "Language",
            ["English", "Hindi"],
        )

    col3, col4 = st.columns(2)

    with col3:
        content_form = st.selectbox(
            "Content Form",
            [
                "Documentary",
                "Explainer",
                "Educational",
                "Storytelling",
                "Tutorial / How-to",
                "Listicle",
                "News / Current Affairs",
                "Other",
                "Custom",
            ],
        )

    with col4:
        length = st.selectbox(
            "Target Length",
            [
                "3–4 minutes",
                "5–6 minutes",
                "8–10 minutes",
                "10–15 minutes",
                "Custom",
            ],
        )

    st.write("")

    # -----------------------------------------------------
    # WRITING PREFERENCES
    # -----------------------------------------------------

    st.markdown(
        '<div class="section-label">WRITING PREFERENCES</div>',
        unsafe_allow_html=True,
    )

    col5, col6 = st.columns(2)

    with col5:
        tone = st.selectbox(
            "Tone",
            [
                "Conversational",
                "Cinematic",
                "Educational",
                "Serious",
                "Friendly",
                "Dramatic",
                "Story-driven",
                "Custom",
            ],
        )

    with col6:
        audience = st.selectbox(
            "Target Audience",
            [
                "General Audience",
                "Children",
                "Students",
                "Young Adults",
                "Professionals",
                "Custom",
            ],
        )

    # -----------------------------------------------------
    # SCRIPT STRUCTURE
    # -----------------------------------------------------

    script_structure = st.text_area(
        "Script Structure / Special Requirements",
        placeholder=(
            "Optional. Tell the system how the script should be structured.\n\n"
            "Examples:\n"
            "• Start with a strong hook and build curiosity.\n"
            "• Use a chronological structure.\n"
            "• Divide the story into 5 clear sections.\n"
            "• Include a strong payoff near the end.\n"
            "• Include sources or historical references."
        ),
        height=135,
    )

    # -----------------------------------------------------
    # CHANNEL STYLE
    # -----------------------------------------------------

    style_instructions = st.text_area(
        "Channel / Script Style Instructions",
        placeholder=(
            "Describe the writing style you want to maintain across your channel.\n\n"
            "Example:\n"
            "Short and medium-length sentences. Natural human narration. "
            "Strong hooks. Frequent paragraph breaks. Avoid robotic wording. "
            "Write for natural voice-over delivery."
        ),
        height=145,
    )

    st.write("")

    if st.button(
        "Generate Script",
        type="primary",
        use_container_width=False,
    ):

        if not topic.strip():
            st.warning("Please enter a topic first.")
        else:
            with st.spinner("Generating your script..."):
                try:
                    generated_script = generate_script(
                        topic=topic,
                        content_form=content_form,
                        language=language,
                        length=length,
                        tone=tone,
                        audience=audience,
                        structure=script_structure,
                        style_instructions=style_instructions,
                    )

                    st.session_state.script_text = generated_script
                    st.session_state.script_workspace = generated_script
                    if st.session_state.project_name.strip():
                        save_project_state()

                    word_count = len(generated_script.split())
                    st.success(
                        f"Script generated successfully — {word_count:,} words."
                    )

                except Exception as e:
                    st.error(f"Script generation failed: {e}")

    # -----------------------------------------------------
    # SCRIPT WORKSPACE
    # -----------------------------------------------------

    if st.session_state.script_text:

        st.divider()

        st.markdown(
            '<div class="section-label">SCRIPT WORKSPACE</div>',
            unsafe_allow_html=True,
        )

        st.text_area(
            "Generated / Edited Script",
            value=st.session_state.script_text,
            height=350,
            key="script_workspace",
        )

# =========================================================
# VOICE
# =========================================================

elif page == "Voice":

    st.title("Voice")

    if not st.session_state.get("project_name", "").strip():
        st.warning("Please create or open a project from Dashboard or Projects before using this stage.")
        st.stop()

    st.markdown(
        '<div class="studio-subtitle">TURN YOUR FISH AUDIO INTO TIMESTAMPED NARRATION</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-label">AUDIO INPUT</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Upload the MP3 you created in Fish Audio. OperoLabs will transcribe it "
        "with word timestamps and create visual-ready narration segments."
    )

    audio_file = st.file_uploader(
        "Upload MP3",
        type=["mp3"],
        key="voice_mp3",
    )

    if audio_file is not None:
        st.audio(audio_file, format="audio/mpeg")

        if st.button("Create Timestamped Segments", type="primary"):
            with st.spinner("Transcribing audio and creating timestamps..."):
                try:
                    transcript, words = transcribe_audio(
                        audio_file.getvalue(),
                        audio_file.name,
                    )

                    segments = build_visual_segments(words)

                    # Save the latest locally generated segments alongside
                    # the transcription for debugging and reuse.
                    VISUAL_SEGMENTS_JSON_PATH.write_text(
                        json.dumps(
                            segments,
                            indent=2,
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )

                    st.session_state.voice_transcript = transcript
                    st.session_state.voice_transcript_workspace = transcript
                    st.session_state.visual_segments = segments
                    if st.session_state.project_name.strip():
                        save_project_state()
                    st.success(
                        f"Done — created {len(segments)} timestamped segments."
                    )

                except Exception as e:
                    st.error(f"Voice processing failed: {e}")

    if st.session_state.voice_transcript:
        st.divider()

        st.markdown(
            '<div class="section-label">TRANSCRIPT</div>',
            unsafe_allow_html=True,
        )
        st.text_area(
            "Transcript",
            value=st.session_state.voice_transcript,
            height=180,
            key="voice_transcript_workspace",
        )

    if st.session_state.visual_segments:
        st.markdown(
            '<div class="section-label">TIMESTAMPED VISUAL SEGMENTS</div>',
            unsafe_allow_html=True,
        )

        # Display timing only: unusually long silent gaps are visually
        # compressed so the list remains easy to follow. The real Whisper
        # timestamps and saved segment data are never changed.
        previous_end = None

        for segment in st.session_state.visual_segments:
            actual_start = float(segment["start"])
            actual_end = float(segment["end"])

            if previous_end is not None and actual_start - previous_end > 4.0:
                display_start = previous_end + 4.0
            else:
                display_start = actual_start

            total_seconds = int(round(display_start))
            minutes = total_seconds // 60
            seconds = total_seconds % 60

            st.markdown(
                f"**[{minutes}:{seconds:02d}]** {segment['text']}"
            )

            previous_end = actual_end

        st.download_button(
            "Download visual_segments.json",
            data=json.dumps(st.session_state.visual_segments, indent=2, ensure_ascii=False),
            file_name="visual_segments.json",
            mime="application/json",
        )

# =========================================================
# VISUAL PLANNER
# =========================================================

elif page == "Visual Planner":

    st.title("Visual Planner")

    if not st.session_state.get("project_name", "").strip():
        st.warning("Please create or open a project from Dashboard or Projects before using this stage.")
        st.stop()

    st.markdown(
        '<div class="studio-subtitle">CREATE VISUAL PROMPTS FROM YOUR NARRATION</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-label">MASTER VISUAL STYLE</div>',
        unsafe_allow_html=True,
    )

    st.text_area(
        "Master Visual Prompt",
        placeholder=(
            "Describe the visual identity you want throughout the project.\n\n"
            "Example:\n"
            "Photorealistic cinematic documentary style, natural lighting, "
            "authentic historical details, 35mm film look, realistic textures..."
        ),
        height=180,
        key="master_visual_prompt",
    )

    col1, col2 = st.columns(2)

    with col1:
        st.text_area(
            "Character / Continuity Instructions",
            key="continuity_instructions",
            placeholder=(
                "Optional. Describe recurring characters, locations "
                "or continuity requirements."
            ),
            height=130,
        )

    with col2:
        st.text_area(
            "Negative Prompt",
            key="negative_prompt",
            placeholder=(
                "Optional. Describe things the image generator should avoid."
            ),
            height=130,
        )

    st.divider()

    if not st.session_state.visual_segments:
        st.info("Complete the Voice stage first. Your timestamped narration will appear here.")
    else:
        st.markdown(
            '<div class="section-label">TIMESTAMPED NARRATION</div>',
            unsafe_allow_html=True,
        )

        # Display timing only: unusually long silent gaps are visually
        # compressed so the list remains easy to follow. The real Whisper
        # timestamps and saved segment data are never changed.
        previous_end = None

        for segment in st.session_state.visual_segments:
            actual_start = float(segment["start"])
            actual_end = float(segment["end"])

            if previous_end is not None and actual_start - previous_end > 4.0:
                display_start = previous_end + 4.0
            else:
                display_start = actual_start

            total_seconds = int(round(display_start))
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            st.markdown(f"**[{minutes}:{seconds:02d}]** {segment['text']}")

            previous_end = actual_end

        if st.button("Generate Visual Prompts", type="primary", use_container_width=True):
            if not st.session_state.master_visual_prompt.strip():
                st.warning("Please enter a Master Visual Prompt first.")
            else:
                with st.spinner("Creating visual prompts..."):
                    try:
                        st.session_state.visual_prompts = generate_visual_prompts(
                            st.session_state.visual_segments,
                            st.session_state.master_visual_prompt,
                            st.session_state.get("continuity_instructions", ""),
                            st.session_state.get("negative_prompt", ""),
                        )
                        if st.session_state.project_name.strip():
                            save_project_state()
                        st.success(
                            f"Done — created {len(st.session_state.visual_prompts)} visual prompts."
                        )
                    except Exception as e:
                        st.error(f"Visual prompt generation failed: {e}")

        if st.session_state.get("visual_prompts"):
            st.divider()
            st.markdown(
                '<div class="section-label">GENERATED VISUAL PROMPTS</div>',
                unsafe_allow_html=True,
            )

            for item in st.session_state.visual_prompts:
                st.text_area(
                    "",
                    value=f"[{item['start']}] {item['prompt']}",
                    height=180,
                    key=f"visual_prompt_{item['start']}",
                    label_visibility="collapsed",
                )

            flow_ready_text = "\n\n".join(
                f"[{item['start']}] {item['prompt']}"
                for item in st.session_state.visual_prompts
            )

            col_a, col_b = st.columns(2)
            with col_a:
                st.download_button(
                    "Download Flow-Ready TXT",
                    data=flow_ready_text,
                    file_name="visual_prompts_flow_ready.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col_b:
                st.download_button(
                    "Download JSON",
                    data=json.dumps(st.session_state.visual_prompts, indent=2, ensure_ascii=False),
                    file_name="visual_prompts.json",
                    mime="application/json",
                    use_container_width=True,
                )

# =========================================================
# IMAGES
# =========================================================

elif page == "Images":

    st.title("Images")

    if not st.session_state.get("project_name", "").strip():
        st.warning("Please create or open a project from Dashboard or Projects before using this stage.")
        st.stop()

    st.markdown(
        '<div class="studio-subtitle">GENERATE YOUR APPROVED VISUAL PROMPTS IN GOOGLE FLOW</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("visual_prompts"):
        st.info("Complete the Visual Planner first. Your generated visual prompts will appear here.")
    else:
        st.markdown(
            '<div class="section-label">READY TO GENERATE</div>',
            unsafe_allow_html=True,
        )

        all_project_prompts = list(st.session_state.visual_prompts)
        output_folder = project_folder(
            folder_name=st.session_state.get("project_folder_name")
            or st.session_state.project_name
        )
        output_folder.mkdir(parents=True, exist_ok=True)

        st.write(f"{len(all_project_prompts)} visual prompts are ready for Google Flow.")

        st.caption(
            "This uses your existing Flow Image Studio automation. Its source files are not modified. "
            "Make sure Google Flow is already open and your existing Chrome/Flow setup is running before starting."
        )

        def worker_process_alive(status):
            """Check the independent Windows worker process, not Streamlit itself."""
            if not status or status.get("worker_type") != "process":
                return False

            pid = status.get("pid")
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                return False

            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=3,
                )
                return str(pid) in result.stdout
            except Exception:
                return False

        folder_name = st.session_state.get("project_folder_name") or st.session_state.project_name
        status_data = read_image_generation_status(folder_name)

        # The previous experimental thread version wrote a status file that
        # used the Streamlit process PID. Never treat that old marker as an
        # active generation job.
        if status_data and status_data.get("worker_type") != "process":
            status_data = None

        worker_alive = worker_process_alive(status_data)

        if status_data and status_data.get("status") == "running" and not worker_alive:
            # The independent worker is no longer alive. Mark the job as
            # stopped so the Generate button becomes available again.
            status_data["status"] = "stopped"
            status_data["message"] = "Worker stopped before completion."
            status_data["error"] = status_data.get("error") or "The image-generation worker is no longer running."
            write_image_generation_status(folder_name, status_data)
            worker_alive = False

        # Always calculate progress from the actual JPGs on disk. The project
        # folder remains the source of truth, even if the UI was refreshed or
        # the app was restarted.
        completed_files = project_image_files(folder_name, all_project_prompts)
        completed_count = len(completed_files)
        total_count = len(all_project_prompts)
        missing_count = max(total_count - completed_count, 0)

        if status_data and status_data.get("status") == "running" and worker_alive:
            current_index = status_data.get("current_index")
            current_timestamp = status_data.get("current_timestamp", "")
            message = status_data.get("message", "Generating...")

            st.info(
                f"⏳ Image generation is running independently — "
                f"{completed_count} / {total_count} completed."
            )

            if current_index:
                if message == "Generating...":
                    st.caption(
                        f"Generating image {current_index} of {total_count}"
                        + (f" — [{current_timestamp}]" if current_timestamp else "")
                    )
                else:
                    st.caption(f"{message} — image {current_index} of {total_count}")

            st.caption(
                "You can move to Script, Voice, Visual Planner, or Projects. "
                "Generation runs in a separate process and will continue while this app remains open."
            )

            if st.button("Refresh Generation Status", use_container_width=True):
                st.rerun()

        else:
            if status_data and status_data.get("status") == "completed":
                failed = status_data.get("failed") or []
                if not missing_count and not failed:
                    st.success(f"🎉 All {total_count} project images are complete.")
                elif failed:
                    st.warning(
                        f"Generation finished: {completed_count} / {total_count} images completed, "
                        f"with {len(failed)} failed prompt(s)."
                    )
            elif status_data and status_data.get("status") in {"stopped", "error"}:
                error_text = status_data.get("error") or "Generation stopped before completion."
                st.warning(
                    f"Image generation is not running. {completed_count} / {total_count} images are complete."
                )
                st.caption(f"Status: {error_text}")
            elif not missing_count:
                st.success(f"All {total_count} project images are already complete.")

            if missing_count:
                if st.button("Generate Images in Flow", type="primary", use_container_width=True):
                    save_project_state()

                    # Recalculate immediately before launching so an image that
                    # completed during a previous run is never generated again.
                    remaining_with_index = [
                        (index, item)
                        for index, item in enumerate(all_project_prompts, start=1)
                        if not image_path_for_prompt(output_folder, item).exists()
                    ]

                    if not remaining_with_index:
                        st.success("All project images are already complete.")
                        st.session_state.generated_image_files = project_image_files(
                            folder_name, all_project_prompts
                        )
                    else:
                        worker_script = Path(__file__).with_name("image_generation_worker.py")
                        if not worker_script.exists():
                            st.error(
                                "The image-generation worker file is missing. "
                                "Please make sure image_generation_worker.py is beside app.py."
                            )
                        else:
                            # Create the marker before launching the process so
                            # a Streamlit rerun cannot create a duplicate worker.
                            total_all = len(all_project_prompts)
                            completed_before_launch = total_all - len(remaining_with_index)
                            initial_status = {
                                "worker_type": "process",
                                "status": "starting",
                                "pid": None,
                                "folder_name": folder_name,
                                "total": total_all,
                                "completed_before": completed_before_launch,
                                "completed_overall": completed_before_launch,
                                "remaining_total": len(remaining_with_index),
                                "completed_this_run": 0,
                                "current_index": remaining_with_index[0][0],
                                "current_timestamp": remaining_with_index[0][1].get("start", ""),
                                "failed": [],
                                "error": None,
                                "message": "Starting...",
                            }
                            write_image_generation_status(folder_name, initial_status)

                            try:
                                creation_flags = (
                                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                                )

                                # Launch the image worker as a truly detached
                                # background process. It has no console/std handles
                                # tied to Streamlit, so closing the launcher/CMD
                                # cannot terminate Flow image generation.
                                worker_python = Path(sys.executable).with_name("pythonw.exe")
                                if not worker_python.exists():
                                    worker_python = Path(sys.executable)

                                process = subprocess.Popen(
                                    [
                                        str(worker_python),
                                        str(worker_script),
                                        folder_name,
                                    ],
                                    cwd=str(worker_script.parent),
                                    creationflags=creation_flags,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    close_fds=True,
                                )

                                initial_status["pid"] = process.pid
                                initial_status["status"] = "running"
                                write_image_generation_status(folder_name, initial_status)

                                st.success(
                                    f"Image generation started in the background — "
                                    f"{completed_before_launch} / {total_all} already complete."
                                )
                                st.rerun()

                            except Exception as error:
                                initial_status["status"] = "error"
                                initial_status["error"] = str(error)
                                write_image_generation_status(folder_name, initial_status)
                                st.error(f"Could not start image generation: {error}")

        # Show any failed prompts from the most recent completed/failed run.
        if status_data and status_data.get("status") == "completed" and status_data.get("failed"):
            st.subheader("⚠️ Failed Generations")
            for failed in status_data.get("failed") or []:
                st.error(
                    f"[{failed.get('timestamp', '')}] {failed.get('prompt', '')}"
                )

        # Refresh the actual image list from the project folder on every rerun.
        st.session_state.generated_image_files = project_image_files(
            folder_name, all_project_prompts
        )

        if st.session_state.get("generated_image_files"):
            st.divider()
            st.markdown(
                '<div class="section-label">GENERATED IMAGES</div>',
                unsafe_allow_html=True,
            )

            image_files = st.session_state.generated_image_files
            for i in range(0, len(image_files), 2):
                cols = st.columns(2)
                for col, image_file in zip(cols, image_files[i:i + 2]):
                    with col:
                        st.image(str(image_file), use_container_width=True)
                        st.download_button(
                            f"Download {image_file.stem}.jpg",
                            data=image_file.read_bytes(),
                            file_name=image_file.name,
                            mime="image/jpeg",
                            use_container_width=True,
                            key=f"download_{image_file.name}",
                        )

# =========================================================
# PROJECTS
# =========================================================

elif page == "Projects":

    st.title("Projects")

    st.markdown(
        '<div class="studio-subtitle">YOUR CONTENT PROJECTS</div>',
        unsafe_allow_html=True,
    )

    active = st.session_state.project_name.strip()
    if active:
        st.markdown('<div class="section-label">CURRENT PROJECT</div>', unsafe_allow_html=True)
        st.info(
            f"{active}  •  Output folder: "
            f"{st.session_state.get('project_folder_name') or active}"
        )

    st.markdown('<div class="section-label">SAVED PROJECTS</div>', unsafe_allow_html=True)

    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    project_dirs = sorted(
        [p for p in PROJECTS_ROOT.iterdir() if p.is_dir() and (p / "project.json").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not project_dirs:
        st.caption("No projects yet. Create your first project from the Dashboard.")
    else:
        for folder in project_dirs:
            folder_name = folder.name
            try:
                data = json.loads((folder / "project.json").read_text(encoding="utf-8"))
            except Exception:
                data = {}

            name = data.get("project_name", folder_name)
            script_done = bool(data.get("script_text"))
            voice_done = bool(data.get("voice_transcript"))
            visual_done = bool(data.get("visual_prompts"))
            prompts = data.get("visual_prompts", []) or []
            image_count = len(list(folder.glob("*.jpg")))
            total_count = len(prompts)

            if total_count:
                image_status = f"{image_count} / {total_count} images"
            else:
                image_status = "0 images"

            st.markdown(f"### {name}")
            st.caption(f"Folder: {folder_name}")

            c1, c2, c3, c4 = st.columns(4)
            c1.write("✓ Script" if script_done else "○ Script")
            c2.write("✓ Voice" if voice_done else "○ Voice")
            c3.write("✓ Visual Planner" if visual_done else "○ Visual Planner")
            c4.write(f"✓ {image_status}" if total_count and image_count == total_count else image_status)

            b1, b2, b3 = st.columns([1, 1, 1])
            with b1:
                if st.button("Open Project", key=f"open_project_{folder_name}"):
                    if load_project_state(folder_name):
                        st.session_state.selected_project_folder = folder_name
                        st.rerun()
            with b2:
                if active and (st.session_state.get("project_folder_name") == folder_name):
                    if st.button("Save Current Project", key=f"save_project_{folder_name}"):
                        autosave_active_project()
                        st.success("Project saved successfully.")
                else:
                    st.caption("Open this project to save changes.")
            with b3:
                if st.button("Delete Project", key=f"delete_project_{folder_name}"):
                    st.session_state.delete_project_confirm = folder_name
                    st.rerun()

            if st.session_state.get("delete_project_confirm") == folder_name:
                st.warning(
                    f"Delete **{name}** and all of its saved files and generated images? This cannot be undone."
                )
                d1, d2 = st.columns([1, 1])
                with d1:
                    if st.button("Confirm Delete", key=f"confirm_delete_{folder_name}", type="primary"):
                        try:
                            shutil.rmtree(folder)
                            if st.session_state.get("project_folder_name") == folder_name:
                                reset_project_session()
                                st.session_state.project_name = ""
                                st.session_state.project_folder_name = ""
                            if st.session_state.get("selected_project_folder") == folder_name:
                                st.session_state.selected_project_folder = ""
                            st.session_state.delete_project_confirm = ""
                            st.success(f"Project deleted: {name}")
                            st.rerun()
                        except Exception as error:
                            st.error(f"Could not delete project: {error}")
                with d2:
                    if st.button("Cancel", key=f"cancel_delete_{folder_name}"):
                        st.session_state.delete_project_confirm = ""
                        st.rerun()

            # A project is opened into the active workspace, and its detail
            # panel below makes the saved content visible without leaving the
            # Projects page.
            if st.session_state.get("selected_project_folder") == folder_name:
                st.divider()
                st.markdown('<div class="section-label">PROJECT DETAILS</div>', unsafe_allow_html=True)
                st.markdown(f"**{name}**")
                st.caption(f"Output folder: `{folder_name}`")

                thumb_files = sorted(folder.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
                detail_cols = st.columns([1, 2])
                with detail_cols[0]:
                    if thumb_files:
                        st.image(str(thumb_files[0]), caption="Project thumbnail", use_container_width=True)
                    else:
                        st.info("No generated image yet.")

                    st.markdown("**Download project files**")

                    script_text = data.get("script_text", "")
                    if script_text:
                        st.download_button(
                            "Download Script",
                            data=script_text.encode("utf-8"),
                            file_name=f"{folder_name}_script.txt",
                            mime="text/plain",
                            use_container_width=True,
                            key=f"download_script_{folder_name}",
                        )

                    segments = data.get("visual_segments", []) or []
                    timestamp_text = "\n".join(
                        f"[{segment.get('start', '')}] {segment.get('text', '')}"
                        for segment in segments
                    )
                    if timestamp_text:
                        st.download_button(
                            "Download Timestamps",
                            data=timestamp_text.encode("utf-8"),
                            file_name=f"{folder_name}_timestamps.txt",
                            mime="text/plain",
                            use_container_width=True,
                            key=f"download_timestamps_{folder_name}",
                        )

                    if prompts:
                        prompt_text = "\n\n".join(
                            f"[{item.get('start', '')}]\n{item.get('prompt', '')}"
                            for item in prompts
                        )
                        st.download_button(
                            "Download Visual Prompts",
                            data=prompt_text.encode("utf-8"),
                            file_name=f"{folder_name}_visual_prompts.txt",
                            mime="text/plain",
                            use_container_width=True,
                            key=f"download_prompts_{folder_name}",
                        )

                    if thumb_files:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                            for image_file in thumb_files:
                                zf.write(image_file, arcname=image_file.name)
                        st.download_button(
                            "Download All Images",
                            data=zip_buffer.getvalue(),
                            file_name=f"{folder_name}_images.zip",
                            mime="application/zip",
                            use_container_width=True,
                            key=f"download_images_{folder_name}",
                        )

                    st.caption("The original project folder remains unchanged.")

                with detail_cols[1]:
                    st.markdown("**Project files**")
                    st.caption("Download what you need from the panel beside the thumbnail. Nothing is required to be downloaded.")

                    if script_text:
                        with st.expander("Preview saved script", expanded=False):
                            st.text_area(
                                "Saved script",
                                value=script_text,
                                height=220,
                                disabled=True,
                                label_visibility="collapsed",
                            )
                    else:
                        st.caption("No script saved yet.")

                    st.markdown("**Timestamped narration**")
                    if segments:
                        st.caption(f"{len(segments)} timestamped segments saved.")
                    elif data.get("voice_transcript"):
                        st.caption("Voice transcript saved, but timestamped segments are not available.")
                    else:
                        st.caption("No timestamped narration saved yet.")

                    st.markdown("**Visual prompts**")
                    if prompts:
                        st.caption(f"{len(prompts)} visual prompts saved.")
                    else:
                        st.caption("No visual prompts saved yet.")

                if total_count:
                    missing = max(total_count - image_count, 0)
                    if missing:
                        st.info(
                            f"Image progress: {image_count} / {total_count}. "
                            f"{missing} image(s) remaining. Go to Images to continue generation; existing images will be skipped."
                        )
                    else:
                        st.success(f"Image progress: {image_count} / {total_count}. All images are complete.")

            st.divider()
