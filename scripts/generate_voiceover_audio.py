#!/usr/bin/env python3
"""
generate_voiceover_audio.py - Ultra-Energetic Studio AI Voiceover Generator for K-CLI
Project Bankai v1.0.0 — Built for AWS "Agents for Humans" Hackathon (Professional Agents Track)
Developer: Krishiv Joshi (@krishivjoshi)

Generates charismatic, high-tempo, studio-quality AI voiceover narration MP3 files
using Microsoft Edge Neural TTS (en-US-ChristopherNeural) at +12% speed and energetic cadence.
"""

import asyncio
import os
import sys
from pathlib import Path

VOICEOVER_SEGMENTS = [
    {
        "filename": "act_1_the_hook.mp3",
        "timestamp": "0:00 - 0:50",
        "title": "Act 1: The Cold Open & 3 Unified UI Tiers Tour",
        "text": (
            "Three AM. Forty-seven failing tests. A three-way merge conflict that makes no sense. "
            "A Rust compiler screaming at you in a language nobody taught in school. "
            "If you've shipped code professionally, you've lived this nightmare! "
            "And the worst part? None of this is hard engineering. It's all noise. "
            "Repetitive, soul-crushing, machine-solvable noise that steals hours from the work that actually matters! "
            "This is K-CLI for Devs! An autonomous background engineering agent built with the AWS Strands Agents SDK "
            "and Amazon Bedrock AgentCore for the Agents for Humans Hackathon. "
            "It runs in your terminal as a full cyberpunk workstation, in your browser as a glassmorphism web dashboard, "
            "or as a lightning-fast mouse-enabled REPL — three complete UIs, one sovereign engine underneath!"
        ),
    },
    {
        "filename": "act_2_strands_and_compilers.mp3",
        "timestamp": "0:50 - 2:10",
        "title": "Act 2: AWS Strands Agent & Closed-Loop Compiler Guardrails",
        "text": (
            "Let me show you something real. I'm not giving it a toy prompt. "
            "I'm asking for a distributed systems architecture — something that would take a mid-level engineer a full afternoon. "
            "Watch what K-CLI does with it! "
            "This is what sets K-CLI apart from every other AI code tool. It does not just generate code and hope for the best! "
            "Powered by the AWS Strands Agents SDK, it catches its own compiler error on the first attempt, "
            "self-heals the type annotation, recompiles to a confirmed green pass, and ONLY THEN stages the patch. "
            "No hallucinated imports. No broken syntax reaching your repo. Closed-loop, compiler-verified engineering!"
        ),
    },
    {
        "filename": "act_3_bedrock_and_daemon.mp3",
        "timestamp": "2:10 - 3:20",
        "title": "Act 3: Autonomous Background Healer Daemon & Amazon Bedrock AgentCore",
        "text": (
            "This is the feature the Professional Agents track was built for! "
            "The daemon runs silently in the background while you focus on building. "
            "I am going to introduce a real bug right now — a broken import in auth_service.py. Watch what happens! "
            "Three seconds. One regression. Zero interruptions! The developer kept building. They will never know it happened. "
            "This is what Agents for Humans actually means — an agent that handles the noise so humans can focus on the signal! "
            "And for enterprise teams — one command exports a complete Amazon Bedrock AgentCore bundle: "
            "OpenAPI action groups and CloudFormation SAM templates, ready to deploy to AWS in minutes!"
        ),
    },
    {
        "filename": "act_4_conflicts_and_chaos.mp3",
        "timestamp": "3:20 - 4:15",
        "title": "Act 4: 3-Way AST Conflict Studio & Chaos Immunity Shield",
        "text": (
            "Standard git merge tools see text. K-CLI sees Python! "
            "It parses the abstract syntax tree of all three versions and semantically merges both feature branches — "
            "keeping what matters from each side. Merge conflict resolved in thirty seconds. No manual editing. Both features ship! "
            "And before bugs find you, K-CLI finds them first! The Chaos Immunity Shield scans for brittle patterns — "
            "None dereferences, silent exception swallowing, missing network timeouts — writes real adversarial pytest suites "
            "against those exact scenarios, and patches the vulnerabilities proactively. "
            "Not reactive debugging. Proactive immunity!"
        ),
    },
    {
        "filename": "act_5_bankai_models_and_finale.mp3",
        "timestamp": "4:15 - 5:00",
        "title": "Act 5: Fine-Tuned Bankai-10B & 7B Models & Grand Finale",
        "text": (
            "And to run all of this, Krishiv Joshi fine-tuned two custom models on Hugging Face — "
            "Bankai-10B for deep architectural reasoning and Bankai-7B for sub-hundred-millisecond rapid responses! "
            "Combined with a sub-millisecond adaptive intent sensor, K-CLI automatically routes casual questions to the fast model "
            "and complex engineering to the frontier model. Always the right intelligence, instantly! "
            "Developers lose hours every day to noise. K-CLI eliminates the noise. It works in the background. "
            "It proves its own code compiles. It heals regressions before you notice them. "
            "And it does it all autonomously — surfacing only when a human decision truly matters! "
            "Built in six weeks. Open source. MIT licensed. K-CLI for Devs — give your developers their hours back. "
            "Clone the repo today!"
        ),
    },
]


async def synthesize_edge_tts(text: str, output_path: Path, voice: str = "en-US-ChristopherNeural"):
    """Synthesizes energetic neural audio using edge-tts with +12% rate and crisp pitch."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice=voice, rate="+12%", pitch="+2Hz")
    await communicate.save(str(output_path))


def generate_audio_tracks(output_dir: str = "demo_assets/voiceover"):
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(f"🎙️ Synthesizing Energetic AI Voiceover Audio in '{out}'...\n")

    has_edge_tts = False
    try:
        import edge_tts
        has_edge_tts = True
    except ImportError:
        pass

    for seg in VOICEOVER_SEGMENTS:
        dest_file = out / seg["filename"]
        txt_file = out / (seg["filename"].replace(".mp3", ".txt"))
        txt_file.write_text(seg["text"], encoding="utf-8")

        print(f"• [{seg['timestamp']}] {seg['title']}")
        print(f"  📝 Script: {txt_file.name}")

        if has_edge_tts:
            try:
                asyncio.run(synthesize_edge_tts(seg["text"], dest_file, voice="en-US-ChristopherNeural"))
                print(f"  🔊 Synthesized Neural MP3: {dest_file.name} (en-US-ChristopherNeural @ +12%)")
            except Exception as e:
                print(f"  ⚠️ edge-tts fallback: {e}")
                try:
                    from gtts import gTTS
                    tts = gTTS(text=seg["text"], lang="en", tld="com", slow=False)
                    tts.save(str(dest_file))
                    print(f"  🔊 Synthesized gTTS MP3: {dest_file.name}")
                except Exception as ex2:
                    print(f"  ⚠️ Error: {ex2}")
        else:
            try:
                from gtts import gTTS
                tts = gTTS(text=seg["text"], lang="en", tld="com", slow=False)
                tts.save(str(dest_file))
                print(f"  🔊 Synthesized gTTS MP3: {dest_file.name}")
            except Exception as ex:
                print(f"  ⚠️ Error: {ex}")

    print(f"\n✔ All {len(VOICEOVER_SEGMENTS)} AI Voiceover audio tracks generated in {out}!")


if __name__ == "__main__":
    generate_audio_tracks()
