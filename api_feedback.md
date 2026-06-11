# 🛠️ Sarvam AI API Developer Experience (DX) Feedback

This document outlines constructive feedback on the developer experience (DX), documentation, and onboarding flow of the Sarvam AI APIs utilized while building **Khabar Suno**.

---

## 1. 📷 Document Intelligence API (Vision)
* **What works well:** The accuracy of the OCR engine for Indian languages (Kannada) is highly impressive. The structural extraction to Markdown format preserves layouts (headers, columns) beautifully.
* **Friction Points (DX):**
  * **ZIP Extraction Overhead:** The API requires downloading output as a ZIP archive. For a simple integration where a developer just wants the extracted string or Markdown text, this introduces unnecessary boilerplate code (requires writing `zipfile` extraction logic in Python).
  * **No Direct Multimodal Chat Support:** Currently, to analyze an image, developers must create a digitization job, upload the image, poll the job, download the ZIP, extract the text, and then send the text to the LLM. 
* **Suggestions:**
  1. Add a direct endpoint to retrieve the output as raw string/markdown content (e.g., `job.get_content_string()`) to save lines of code.
  2. Implement native multimodal support in the `sarvam-30b` chat API (allowing image inputs directly in the messages payload, like `gpt-4o`).

---

## 2. 🎙️ Text-to-Speech (TTS - Bulbul:v3)
* **What works well:** The `shubh` Kannada voice model is incredibly warm, clear, and sounds like a natural native speaker rather than a robotic translation voice. Latency is minimal, which is ideal for real-time WebRTC assistants.
* **Friction Points (DX):**
  * **Advanced Audio Controls:** Fine-tuning speed (`pace`) is supported, but there is lack of clear documentation on how to control pitch, volume, or add specific pauses (using SSML or custom tags).
* **Suggestions:**
  1. Support SSML (Speech Synthesis Markup Language) or custom Markdown-like tags (e.g., `[pause: 500ms]`) in the prompt to allow developers to build more theatrical or expressive narrations.

---

## 3. 🗣️ Speech-to-Text (STT - Saaras:v3)
* **What works well:** Excellent transcription quality for spoken Kannada. It handles code-mixing (switching between English and Kannada words in a single sentence) exceptionally well, which is crucial for modern Indian users.
* **Friction Points (DX):**
  * **Streaming / VAD Integration:** Setting up real-time audio chunking and Voice Activity Detection (VAD) requires extensive custom pipelines.
* **Suggestions:**
  1. Provide code recipes in the official documentation for standard real-time frameworks (e.g., Pipecat, LiveKit, WebRTC) to reduce setup time for conversational voice bots.

---

## 4. 🧠 LLM (Sarvam-30b)
* **What works well:** Highly responsive, handles system instructions cleanly, and produces culturally accurate Kannada summarizations without literal translation artifacts.
* **Friction Points (DX):**
  * **Documentation & OpenAI Compatibility:** While it supports OpenAI compatibility, the base URL endpoints and header keys (`api-subscription-key` vs standard Bearer token header) could be documented more visibly in the quickstart guides to make drop-in replacement simpler.
* **Suggestions:**
  1. Standardize authentication headers to accept Bearer tokens alongside the subscription key header to make integration with third-party libraries even more seamless.
