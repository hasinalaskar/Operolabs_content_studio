# 🎬 OperoLabs AI Content Studio

> **From idea to finished visuals — one AI-powered content workflow.**

OperoLabs AI Content Studio is a Streamlit-based AI content creation workspace designed to bring multiple stages of content production into one streamlined workflow.

Instead of moving between several disconnected tools, OperoLabs organizes the content-production process into one structured pipeline:

**📝 Script → 🎙️ Voice → 🎨 Visual Planner → 🖼️ Images → 📁 Projects**

The goal is to make AI-powered content production more organized, repeatable, and easier to manage.

---

## ✨ What is OperoLabs?

Creating AI-powered videos often requires switching between multiple tools for:

- Script writing
- Voice generation and transcription
- Visual planning
- Image generation
- File organization
- Project management

OperoLabs brings these stages together inside a single workspace.

The application is built with **Python** and **Streamlit**, with AI services and browser-based image generation integrated into the workflow.

---

# 🚀 Workflow

## 1. 📝 Script

The Script stage is where the content begins.

Users can define:

- Topic
- Target duration
- Content requirements
- Additional instructions

OperoLabs generates a structured script based on the selected requirements and target duration.

The workflow uses duration-based word-count targets to help keep the generated script aligned with the intended video length.

### 🎯 Goal

Create a narration-ready script before moving into production.

---

## 2. 🎙️ Voice

Once the script is ready, the workflow moves to the Voice stage.

The narration is processed and converted into timestamped transcription data.

The transcription is divided into natural visual segments so that the narration can later be matched with appropriate visuals.

Example:

```text
[0:00] In the heart of the bustling streets of Hyderabad,

[0:03] a tantalizing aroma wafts through the air,

[0:06] drawing in food lovers from all corners of the city.

```

Each segment contains timing information that is used by the Visual Planner.
### 🎯 Goal

Convert narration into structured, time-aligned segments that can drive the visual workflow.

## 3. 🎨 Visual Planner

The Visual Planner transforms the narration into visual scenes.
For each narration segment, the system creates a corresponding visual concept and prompt.
The planner can use:

- 🎬 Scene descriptions
- 🎨 Master visual style
- 🔄 Continuity instructions
- 🚫 Negative prompts
- ⏱️ Narration timestamps
  
This creates a structured visual plan before image generation begins.
🔄 Workflow

Narration → Timestamp → Visual Scene → AI Image Prompt

### 🎯 Goal

Ensure every part of the narration has a corresponding visual direction before image generation.

## 4. 🖼️ Images

The Images stage connects the visual prompts to the image-generation workflow.
OperoLabs sends the prepared prompts to the Flow image-generation engine and tracks the generation progress.

The workflow supports:
- 🖼️ Sequential image generation
- 📊 Generation progress
- ⚠️ Failed prompt tracking
- 📁 Project-specific output folders
- 🔄 Resume capability
  

The image-generation engine is kept separate from the main Streamlit interface so the browser-based generation workflow can operate independently.

### 🎯 Goal

Turn the visual plan into a complete set of images ready for the next stage of content production.

## 🌐 Chrome Keep Alive Extension

OperoLabs uses a lightweight Chrome Keep Alive extension as part of the browser-based image-generation workflow.

The extension helps keep the Google Flow browser session active while images are being generated.

This allows the user to:

- 🌐 Move away from the Google Flow tab
- 🔄 Keep the Flow session active during generation
- 🖼️ Continue image generation while working elsewhere
- ⚙️ Support longer-running browser-based generation workflows

The extension works alongside the Flow image-generation engine and is separate from the main Streamlit interface.

### Image Generation Workflow

**OperoLabs → Flow Image Engine → Google Flow → Chrome Keep Alive → Generated Images**

## 5. 📁 Projects

Projects provide a persistent workspace for each content creation job.
Each project keeps important information and generated assets organized together.
A typical project can contain:

```
Project
├── project.json
├── script.txt
├── transcription.txt
├── visual_segments.json
├── visual_prompts.json
└── generated images

```
This keeps different content projects separated instead of mixing all generated files together.

### 🎯 Goal

## 🔄 Resume Image Generation

One of the important features of the Projects system is the ability to resume an interrupted image-generation job.
For example:

Required images:   40
Completed images:  18
Remaining images:  22

When a project is reopened, OperoLabs checks the existing project folder and identifies which images have already been generated.
Instead of generating everything again, the workflow can continue with the remaining prompts.
This helps prevent:

- ❌ Duplicate image generation
- ❌ Unnecessary API usage
- ❌ Losing progress
- ❌ Rebuilding an entire project after an interruption
  
### 🧩 Architecture

At a high level, the workflow looks like this:
Create a structured workspace that can be saved, reopened, and continued later.

```
                    ┌───────────────┐
                    │   📝 SCRIPT   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   🎙️ VOICE    │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────────┐
                    │ 🎨 VISUAL PLANNER │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │    🖼️ IMAGES      │
                    │                   │
                    │ Flow Image Engine │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │    📁 PROJECTS    │
                    └───────────────────┘

```
## 🛠️ Technology Stack

Technology	Purpose
🐍 Python	Core application logic
🎛️ Streamlit	User interface
🤖 OpenRouter	AI model access
🎙️ Whisper	Audio transcription
🌐 Playwright	Browser automation
🖼️ Google Flow	AI image generation workflow
📁 JSON	Project and workflow data
🔧 Git / GitHub	Version control

## 📂 Project Structure

```
OperoLabs-Content-Studio/
│
├── app.py
├── flow_engine.py
├── image_generation_worker.py
├── requirements.txt
├── .gitignore
├── operolabs_logo.png
├── README.md
│
└── screenshots/

```
## 🎯 Design Philosophy

OperoLabs is built around a simple principle:
Create once. Organize everything. Continue where you stopped.

The application is designed to reduce repetitive manual work while keeping the content-production process understandable and controllable.
Rather than creating an enormous collection of disconnected AI tools, OperoLabs focuses on connecting the important stages of a real content workflow.

## 🔐 Security

Sensitive credentials and local configuration files should never be committed to GitHub.
Examples include:

```
.env
API keys
Access tokens
Local credentials

```
These files should remain local or be provided through secure environment variables or secrets when deploying the application.
The repository includes a .gitignore file to help prevent sensitive and local files from being committed accidentally.

## 🚧 Project Status

OperoLabs AI Content Studio is currently under active development.
Current workflow
- ✅ Script generation
- ✅ Voice transcription
- ✅ Timestamped visual segmentation
- ✅ Visual planning
- ✅ AI image generation
- ✅ Image generation progress tracking
- ✅ Project creation
- ✅ Project saving
- ✅ Project reopening
- ✅ Image-generation resume workflow
- 🚧 Further deployment and production improvements

## 🗺️ Future Direction

Planned improvements may include:
- ☁️ Cloud deployment
- 👤 User accounts
- 💾 Persistent cloud storage
- 📊 Advanced project dashboards
- 🎬 Complete video assembly workflow
- ⚙️ Additional automation
- 🔌 Additional AI providers
- 🚀 Production-ready infrastructure

## 👩‍💻 About
OperoLabs AI Content Studio is an independent project focused on building practical AI-powered automation for modern content production.
The project explores how AI, automation, browser workflows, and structured project management can work together to simplify creative production.

## ⭐ Support the Project

If you find OperoLabs interesting, feel free to explore the repository, follow the development, and share your feedback.
OperoLabs — turning ideas into structured AI content workflows. 🎬✨
