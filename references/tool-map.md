# Mapa de ferramentas por tipo

Cada helper de `helpers/` aparece aqui **uma vez**, no tipo em que é usado.
Argumentos, ordem e regras estão no `SKILL.md` (seção Helpers) e na referência
indicada. O teste `tests/test_catalog.py` falha se um helper novo não for
adicionado a este mapa, ou se um item do mapa deixar de existir.

"Interno" = chamado por outro helper, não direto pelo agente.

| Tipo | Helpers | Referência |
|---|---|---|
| **Ingestão e inventário** | `ingest_url`, `quality_probe`, `inventory`, `scene_detection`, `watch_video`, `contact_sheet`, `timeline_view`, `take_analyzer` | `SKILL.md` Fase 1 |
| **Transcrição e revisão** | `transcribe`, `transcribe_batch`, `parakeet_engine` (interno de `transcribe`), `pack_transcripts`, `revise_transcript`, `second_listen`, `spoken_notes`, `hesitations`, `diarize` | `transcription.md`, `transcript-review.md` |
| **Corte (Fase 1)** | `speech_regions`, `speech_level`, `voice_levels`, `refine_edges`, `build_edl`, `render`, `verify_cut`, `sync_sources`, `multicam`, `stabilize`, `chapters` | `SKILL.md` Fase 1, `multicam.md`, `longform.md` |
| **Enquadramento** | `reframe`, `face_track`, `safe_layout` | `shortform.md` |
| **Cor** | `detect_color`, `auto_color`, `grade`, `color_pipeline`, `film_look`, `hdr_lut` (interno de `render`) | `log-grade.md`, `color-multitake.md` |
| **Legendas** | `caption_style`, `captions_srt`, `captions_for_remotion`, `highlight_words` | `shortform.md`, `longform.md` |
| **Motion e Fase 2** | `scaffold_phase2`, `render_phase2`, `build_hyperframes`, `export_hyperframes`, `hf_motion_scenes`, `hf_pull_takes`, `hf_version`, `hf_parity`, `inserts_plan`, `broll_plan`, `make_card` | `hyperframes-engine.md`, `hyperframes-traps.md`, `motion-craft.md`, `direction.md`, `scenes.md` |
| **Ritmo e cinema** | `beat_map`, `beat_edit`, `speed_ramp`, `cinema_edit` | `beat-sync.md`, `cinema-motion.md` |
| **VFX e composição** | `chroma_key`, `person_matte`, `matte_refine`, `composite`, `detect_plane`, `camera_track`, `camera_solve`, `camera_solve_colmap` | `compositing.md`, `OPUS-VFX-3D.md` |
| **Áudio** | `audio_chain`, `music_carve`, `volume_envelope`, `sfx_events`, `sfx_index`, `sfx_peak`, `sfx_synth`, `epidemic_music`, `treblo_music`, `earshot_sfx`, `deliver_mix` | `sfx-craft.md`, `soundtrack.md` |
| **Mídia e licença** | `pexels_search`, `wikimedia_images`, `google_images`, `media_ledger` | `SKILL.md` (Helpers) |
| **QA e verificação** | `qa_mix`, `motion_gates`, `lint_undefined`, `regress` | `critic-gauntlet.md`, `sfx-craft.md` §14, `motion-craft.md` §2.1 |
| **Clipping e viralização** | `clip_finder`, `viral_score` | `external-video-skills.md` #28–#33 |
| **Preview e estado da edição** | `preview_server`, `watch_edits`, `apply_preview_edits`, `agent_markers`, `staleness` | `SKILL.md` (Preview) |
| **Gosto e aprendizado** | `client_profile`, `learnings` | `SKILL.md` (gate de Estilo) |
| **Entrega** | `deliveries`, `publish` | `SKILL.md` (Entrega) |
| **Modelos de edição** | `modelos`, `modelos_receitas`, `modelos_demo`, `cenas`, `cenas_titulo`, `cenas_lyric` (cenas HyperFrames montadas por dados: card-ficha, titulo-misto, lyric-carro) | `modelos/README.md` |
| **Biblioteca externa** | `external_skills` | `external-video-skills.md` |

## Checks obrigatórios por momento

| Momento | Check |
|---|---|
| Antes de rodar um helper recém-editado | `lint_undefined.py` (nome indefinido = NameError no render) |
| Depois de mudar um helper da Fase 1 | `regress.py` |
| Depois de mudar o pipeline da Fase 2 | `regress.py --phase2` |
| Depois do corte | `verify_cut.py` |
| Antes de mostrar a Fase 2 | `safe_layout.py --report`, `qa_mix.py`, `motion_gates.py all`, crítico (`critic-gauntlet.md`) |
