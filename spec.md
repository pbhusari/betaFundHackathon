Project: Synthetic Aerial Edge-Case Generator

Working name: TBD (placeholder: Mirage-Air or SkyAugment)
Hackathon: Beta Super Hackathon, May 2 2026, Computer History Museum
Track: Track 4 — Physical AI + Simulation
Submission deadline: 1:00 PM (late window until 2:00 PM)
Deploy target: Butterbase (MCP submission required)


1. The Pitch (one paragraph)
Drone perception models (obstacle avoidance, landing-zone classification, object detection) are blocked by the cost and risk of collecting real flight data. ArduPilot SITL + Gazebo gives free flight trajectories with ground-truth labels — but the renders look like a video game. We take SITL/Gazebo footage plus a natural-language scenario ("dust storm at low sun angle over desert") and use Seedance 2.0's reference-to-video to generate photorealistic variants that preserve the original trajectory and object placement. Output: labeled photorealistic flight footage at a fraction of the cost of real flight hours. The recommender layer suggests which edge cases matter based on the user's existing dataset gaps.
Buyer: Defense/commercial drone companies (Anduril, Shield AI, Skydio, Zipline, Percepto) and aerial CV teams blocked on training data diversity.
Why now: Seedance 2.0 (April 2026 GA) is the first commercial video model with multi-reference conditioning that can preserve scene structure across generations. Research papers exist (CRAFT, RoboTransfer, FlightDiffusion) but no productized tool.

2. Judging Rubric Alignment
DimensionWeightHow we hit itTech Execution30%Real SITL→Gazebo→Seedance→labels pipeline. Multi-step agent reasoning over scenario expansion. Not a UI wrapper.GTM & Moat25%Vertical-specific (aerial perception). Named buyers. Domain expertise (founder ex-cleared/defense-adjacent).Continuity20%Slots into Mirage cyber-range product portfolio. 7-day plan: real customer outreach to 3 named drone companies.UX Innovation15%Drop a sim clip, type a scenario, get labeled training data. One-click.Demo Impact10%Side-by-side: ugly Gazebo render vs. cinematic generated variant, with bbox labels transferred. Visceral.
Beta Fund dog-whistle: They want agents, not wrappers. The agent in this product is the Scenario Reasoner that expands a user's vague edge-case description into N structured Seedance reference prompts, scoring each for diversity vs. the user's existing dataset. That's the agentic story.

3. Scope for 3.5 hours (be ruthless)
MUST HAVE (P0) — without these we don't ship

 Web UI on Butterbase: file upload (sim clip or single frame), prompt textbox, "Generate" button, results grid
 Pre-recorded SITL/Gazebo flight clip baked in as a default demo asset (do NOT make the judge wait for a sim to run live)
 One working call to Seedance 2.0 reference-to-video with the uploaded frame as reference
 Display 3-4 generated variants side-by-side with the original
 One slide: "How it works" architecture diagram
 Pre-recorded 2-min demo video for submission

SHOULD HAVE (P1)

 Z.AI scenario expansion: short prompt → structured Seedance prompt JSON (lighting, weather, terrain, time-of-day)
 MAVLink label overlay: parse a .tlog or .bin from the SITL run, draw bbox/trajectory on both original and generated
 Cache results so demo doesn't depend on live API
 Cost estimator: "this dataset would cost $X to collect via real flight hours, $Y via our service"

NICE TO HAVE (P2 — only if P0 + P1 done with 30 min to spare)

 Recommender: "your existing dataset is missing X, Y, Z conditions" — diff a user's described conditions vs. a known taxonomy
 Multiple variants per prompt with diversity scoring
 Export as ZIP with labels in COCO/YOLO format

EXPLICITLY OUT OF SCOPE

Live SITL execution during demo (pre-record everything)
Training a downstream model (we generate data, we don't train)
Trajectory-exact preservation (claim "same scene, different conditions" — weaker but defensible)
Real-time generation (Seedance takes 30-60s per clip; that's fine, just don't promise real-time)


4. Architecture
┌─────────────────┐
│ Butterbase UI   │  ← Next.js or simple HTML+JS
│ (upload + form) │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ Backend (Butterbase fn or   │
│ FastAPI on Butterbase)      │
└────────┬────────────────────┘
         │
         ├─► [Z.AI]   short prompt → structured scenario JSON
         │
         ├─► [Seedance 2.0] reference-to-video API
         │   - input: user frame + structured prompt
         │   - output: video URL (5s clip @ 720p)
         │   - tier: seedance-2-fast for iteration
         │
         ├─► [optional] MAVLink label parser → overlay
         │
         └─► return: { variants: [{video_url, prompt, labels}] }
                    │
                    ▼
            Display grid in UI
Critical API notes (verified from BytePlus docs)
Seedance 2.0 endpoints:

text-to-video — prompt only
image-to-video — single ref image + prompt
reference-to-video — up to 9 images + 3 videos + 3 audios. Use this one for our case.
Tiers: Fast (use for iteration), Standard (use for final demo render), Pro (skip)
Model invocation is asynchronous — submit task, poll for completion. Wrap in async/await.
Base URL: https://ark.ap-southeast.bytepluses.com/api/v3
SDK: pip install byteplus-python-sdk-v2 (or call REST directly)
API keys provided in handbook (4 keys — round-robin if rate-limited)

Z.AI:

API key in handbook
Use for prompt expansion (structured output mode preferred)
Schema: {lighting, weather, terrain, time_of_day, atmospheric_effects, camera_artifacts}

Butterbase:

Submission code: butterbase0502
Promo code for $20 credit: BUTTERBASE0502
Connect via Butterbase MCP for deployment
Bonus points if built AND deployed on Butterbase


5. Demo assets we need before coding
Prep these FIRST (15-20 min) so the rest of the build has real inputs:

One Gazebo+SITL flight clip — 10 seconds, 720p, MP4. Easiest path:

Pull a public ArduPilot+Gazebo demo video from YouTube as fallback if SITL setup chews time
Or use Iris quadcopter + iris_runway world (standard ArduPilot demo)
Save first frame as PNG separately for image-ref input to Seedance


A .bin or .tlog MAVLink log — for the labels feature. If skipping P1, ignore.
3-5 pre-baked scenario prompts ready to paste:

"Dust storm over desert terrain, low sun angle, particulate haze"
"Heavy rain, dusk, urban environment with reflective wet pavement"
"Snow flurries, overcast, mountainous terrain, low visibility"
"Clear midday over agricultural fields, harsh shadows"
"Foggy morning over coastal cliffs, soft diffuse light"


3-5 pre-generated Seedance outputs for these prompts, cached locally. The live demo should never depend on a live API call. Generate ahead, cache, fall back to live only if everything works.


6. Step-by-step execution plan
Hour 0 (T+0 to T+30 min): De-risk

 Verify Seedance API key works with a simple text-to-video call (any prompt)
 Check that aerial-perspective output looks reasonable — generate one test clip with a drone POV prompt
 If aerial perspective looks bad: PIVOT. Reframe as "ground vehicle" (autonomous driving) or "fixed CCTV" (security). Same product shape, different framing.
 Sign up for Butterbase, redeem promo, connect MCP

Hour 1 (T+30 to T+90 min): Core pipeline

 Get one input frame → Seedance reference-to-video → output URL working in a Python script
 Wire Z.AI structured prompt expansion (input: short text, output: JSON spec)
 Combine both: short user prompt → expanded JSON → Seedance call → video URL

Hour 2 (T+90 to T+150 min): UI + Butterbase deploy

 Minimal Butterbase app: upload frame, prompt textbox, "Generate" button
 Backend handler invokes the pipeline from Hour 1
 Results grid: original frame + N generated variants in <video> tags
 Cache layer: pre-computed results for the 3-5 demo prompts so live demo is instant
 Deploy. Verify public URL works on a phone.

Hour 3 (T+150 to T+210 min): Polish + demo

 Architecture slide (3 boxes: Gazebo → Agent → Seedance)
 Cost-comparison line: real flight hours $X/hr vs. our generation $Y/clip
 Record 2-min demo video (60s product, 30s architecture, 30s vision)
 Submit via Butterbase MCP with code butterbase0502

Final 30 min (T+210 to T+240): Buffer

Things will break. Reserve this for fixes.
If everything works: add the labels overlay (P1).


7. Pitch deck (3 slides — strict format from handbook)
Slide 1 — Team

Founder: Pranav Bhusari — Security + ML Engineer, ex-Cromulence/Parsons (DARPA/NSA-adjacent CNO), MS Purdue CERIAS, ex-LLNL/Peraton/Alif
Operating: Purdue Analytics LLC (Mirage cyber range, Dragnet ICS honeypot, Kaiju RE+LLM tooling)
Team-problem fit: Direct experience with synthetic data pipelines, sim environments, and the defense/dual-use buyer

Slide 2 — Product

One-liner: Photorealistic edge-case footage for aerial perception models, generated from cheap simulation data.
Problem: Drone CV teams blocked by lack of diverse real flight data. Real flights cost $200-2000/hr; rare conditions (storms, dust, dusk) are expensive or dangerous to capture.
Solution: Type a scenario, drop a sim clip, get N labeled photorealistic variants in 60 seconds. Powered by Seedance 2.0 reference-to-video + Z.AI scenario reasoning agent.
Market: 50+ named drone/AV companies + DoD test ranges. TAM via synthetic data market ($2.4B, growing 35% YoY).

Slide 3 — Demo

2-min embedded video
Shows: input clip (Gazebo) → user types scenario → generated photorealistic variants side-by-side → labels transferred
Closing: "Already integrated with ArduPilot SITL — works out of the box for the 100K-strong open-source drone community."


8. Risks & mitigations
RiskLikelihoodMitigationSeedance bad at aerial perspectiveMediumTest in first 30 min; pivot to ground/CCTV framing if neededAPI rate limits during demoMediumCache all demo outputs; live demo is fallback to cachedButterbase MCP setup eats timeMediumSet up first thing; if blocked >30 min, deploy to Vercel/Render and submit via MCP afterSITL/Gazebo install on hackathon laptop failsHighUse pre-recorded clips from YouTube or public datasets; don't need live SITLTrajectory not preserved across variantsHighDon't promise it. Pitch as "same scene, varied conditions" not "same trajectory, varied conditions"Judge asks "why not procedural domain randomization?"HighAnswer: photorealism for real-camera sensor characteristics, atmospheric effects, sub-pixel realism that procedural can't match

9. Continuity story (week-1 plan after hackathon)
Beta Fund cares about this 20%. Have a real answer.

Day 1-2: Cold-email 10 named drone perception leads (Skydio, Shield AI, Anduril, Percepto, Zipline)
Day 3-4: Open-source ArduPilot integration plugin → release on r/ArduPilot, ArduPilot Discord (10K+ users)
Day 5: Apply to Beta University Cohort 11
Day 6-7: Generate first 100-clip dataset publicly, post to HuggingFace as "AerialEdgeCase-100"
Month 1: First paying design partner ($5K/mo for 1000 clips/mo)
Quarter 1: Productize as Purdue Analytics offering; integrate with Mirage cyber-range as the perception-data module


10. Files & environment
API Keys to set as env vars (do NOT commit to repo):
bashexport SEEDANCE_API_KEY=<one of the 4 from handbook>
export ZAI_API_KEY=<from handbook>
export BUTTERBASE_TOKEN=<from butterbase signup>
Hackathon API keys are SHARED across all attendees — do not push to public GitHub. Use .env + .gitignore.
Suggested repo structure:
.
├── README.md
├── .env.example
├── .gitignore
├── backend/
│   ├── main.py            # FastAPI or Butterbase function entry
│   ├── seedance_client.py # async wrapper around Seedance API
│   ├── zai_agent.py       # scenario expansion
│   └── label_transfer.py  # MAVLink → bbox overlay (P1)
├── frontend/
│   └── index.html         # minimal upload UI
├── demo_assets/
│   ├── gazebo_clip.mp4
│   ├── gazebo_frame.png
│   └── cached_outputs/
└── deck/
    └── slides.pdf

11. Things to remember

Beta Fund wants agents not wrappers. Frame the Z.AI scenario reasoner as the agent.
BytePlus wants Seedance API consumption. Use the multi-reference endpoint, not just text-to-video.
Continuity story is 20% of the grade. Don't skip slide content on this.
Submission deadline is 1 PM hard. Late window 1-2 PM is rolling, no guaranteed slot.
Bonus points for being deployed on Butterbase.
Demo video must be embedded in deck, not a broken link.
Exactly 3 slides. Non-compliant submissions may not be reviewed.


12. Open questions for Claude Code to figure out

Best HTTP/SDK pattern for async Seedance task polling
Cleanest way to overlay MAVLink labels on the generated video (ffmpeg? canvas?)
Whether Butterbase supports long-running async tasks or if we need a webhook pattern
Z.AI structured output schema details (some providers need explicit JSON schema, some don't)
Whether the input "single frame" should actually be a 1-2s video clip for better Seedance conditioning