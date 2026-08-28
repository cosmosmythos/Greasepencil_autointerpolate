---
name: plain-speak
description: Use when explaining ANY TextureSynth concept, code, feature, architecture, or research to the user. The user is a junior technical 3D artist new to computer graphics programming — speak plain language, define every term on first use, ban jargon, use concrete analogies. Trigger words: explain, educate, teach, "like I'm", jargon, ELI5, "what does X mean", "what is the point of".
---

# Plain-Speak (Explain Like I'm a Junior 3D Artist)

## The audience

The user is a junior technical 3D artist. They know Blender deeply: meshes, UV
unwrapping, seams, islands, textures, materials, node editors, basic Python.
They do NOT have: C++, linear algebra fluency, GPU or shader background, or
graphics-research background.

Every explanation must assume zero computer-graphics-programming context,
even when the topic is "simple" to an engineer.

## Rules

1. **Define every term on first use** — one plain sentence, with a concrete
   analogy from the artist's world when possible. Never reuse a term defined
   earlier without it already being understood.
2. **No jargon dumps** — terms like "adjacency cable", "uv_derivative",
   "tangent_xform", "mip selection", "push constants", "bindless",
   "barycentric", "SSBO", "half-edge", "rasterizer pre-pass" are NOT allowed
   unexpanded. Use the translation table below.
3. **Papers do not explain themselves** — never cite a paper title as if it
   means something. If research is relevant, say in ONE plain sentence what
   that work gives us (e.g. "a paper showing how to store per-face neighbor
   links so filtering works across seams").
4. **No acronyms without expansion** — GPU, CPU, UV, GLSL, SSBO, AO, PBR,
   VDB: spell out what they stand for at least once, then you may use them.
5. **One idea per bullet** — short bullets and paragraphs. No dense walls.
6. **Lead with the artist view** — say what the artist does in Blender
   first, then what the engine does. The user's mental model is Blender, not
   Vulkan.
7. **Use their concrete examples** — a blur node, a cube with a seam, a
   texture island: pick real, visual examples over abstract descriptions.

## Translation table

| Jargon | Plain meaning |
|---|---|
| adjacency / adjacency cable (Copernicus) | A map that tells each texture pixel who its REAL surface neighbor is, across seams |
| neighbor map / correspondence map | The map itself: for seam pixels, where their mirror pixel lives |
| border_mask | A yes/no stencil: "is this pixel near a seam?" |
| uv_adjacency | The mirror UV: where my surface-neighbor lives in the texture |
| primid | Which triangle this pixel belongs to |
| primuv | Where inside that triangle the pixel sits |
| tangent_xform | The rotation that lines up one island's directions with its neighbor's (so vectors point the right way across seams) |
| uv_derivative | How fast texture coordinates change between neighboring pixels; used so the GPU picks the right sharpness level |
| mip / mipmap | Pre-blurred copies of a texture; the GPU picks one based on distance |
| push constants | A small envelope of numbers the CPU hands the GPU with each job |
| bindless | All textures on one big shelf; nodes grab a slot number instead of a fixed socket |
| SSBO | A buffer of raw numbers the shader can read and write |
| half-edge | An edge that remembers its two neighboring faces — enough memory to walk across seams |
| rasterizer | The program that paints a mesh into a texture, pixel by pixel |
| barycentric coordinates | "How much of each corner" — weights that blend values across a triangle |
| GLSL | The language shaders are written in |
| compute pass / dispatch | A program that runs over every pixel at once, in parallel |
| tangent space / tangent frame | A local x/y/z axis grid glued to each point of the surface |
| FetchContent | A build-system helper that downloads a library automatically |
| header-only | A library that is just .h files — nothing to compile, just include |

## Examples

Bad: "The geometry rasterizer emits primid/primuv/tangent_xform channels into
the adjacency cable so seam-aware nodes can redirect sampling."

Good: "Think of unwrapping a cube. Each face becomes a flat island. Where two
islands touch in 3D but not in the texture, that's a seam. We paint extra
information into the texture: for every pixel near a seam, a note saying
'my real neighbor lives at THIS other spot in the texture'. A blur node then
checks the note before sampling, and looks at the right pixel — so the blur
stops leaving a visible line at the seam."