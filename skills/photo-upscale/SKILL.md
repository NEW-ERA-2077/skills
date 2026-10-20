---
name: flowers-upscale
description: "Enhance blurry, soft, or low-quality photos into clearer, more natural-looking images using 2–3 contextual AI refinement passes and carefully blended crops. Improves visual detail and clarity without increasing image dimensions: a 1K image stays 1K, not 4K or 8K."
metadata:
  version: "1.0.0"
  display_name: "flowers_upscale"
---

# flowers_upscale

Improve the **visual quality** of an existing photo, not its pixel count. Recover or plausibly reconstruct fine-looking detail, reduce blur and inherited artifacts, and preserve a photographic appearance. **Never enlarge the final image to a higher resolution**: keep exactly the source width and height, aspect ratio, framing, and orientation. A cleaner 1K photo is still 1K, not 4K or 8K. If accurate detail is missing from the source, do not present reconstructed texture as authentic recovered information.

Use the uploaded image as the authority for identity, anatomy, shape, composition, colors, and lighting. Default to **two refinement passes**; use a third pass when requested or when distinct focal details still need careful work. Do not require a technical questionnaire when the user's request is clear. Discover available AI image-editing and raster-processing tools before starting; use environment-native paths and tools, and report any unavailable essential capability rather than claiming an unperformed enhancement. Preserve the original file and keep intermediate results separate.

## 1. Context-aware detail enhancement

Work on overlapping crops so the image editor can concentrate on small details without changing the overall scene. For **every** AI editing call, provide both the untouched original image as a **reference** and the current crop as the **editing target**. Never send a crop alone. Inspect each region first, include only relevant material-specific instructions, and request that the edited crop retain precisely the same contents, framing, and geometry. Record each crop's box in source-image coordinates, the editing prompt, and the actual dimensions of the returned image. Independent crop edits may run concurrently if supported; save their outputs as soon as they finish.

**Pass 1 — Overall clarity.** Divide the source into a 3 × 3 grid of core regions. Extend each core by **20% of its width and height on each side**, clipped to image bounds, producing nine overlapping crops. Enhance those crops, align them back to the original, and blend them into the first full-image result. **Do not resize the assembled result to 4K, 8K, or any other enlarged target.** Its dimensions must equal the source dimensions.

**Pass 2 — Important details.** Inspect the first result and select **4–8 overlapping regions of interest** with meaningful visible structure, such as faces, hair, hands, objects, or fabrics. Use the original photo for contextual reference and the current result for crop selection. Enhance and blend these regions into the second full-image result. Skip low-information areas that would benefit little or invite invented texture.

**Optional pass 3 — Focal precision.** If selected, inspect the second result and refine **4–8 tighter focal regions**, such as eyes, lips, noses, fingers, or distinctive material details, where actually present. Retain consistent geometry and repeated or paired features. Merge into the third full-image result. Do not force a third pass where it would add artifacts rather than clarity.

## 2. Photographic fidelity and controlled reconstruction

Use the following principles in the image-editing prompts, tailored to the content of each crop:

> The original image is the authority for identity, anatomy, pose, expression, clothing, object shapes, colors, lighting, and composition. The target crop defines the exact framing and geometry to return. Improve perceived optical clarity and recover or plausibly reconstruct restrained photographic detail while preserving natural focus falloff, genuine imperfections, and smooth transitions. Remove inherited blur-related artifacts where possible, without inventing new structures, symbols, or marks. Avoid beautification, relighting, oversharpening, halos, ringing, embossed or crosshatched textures, repetitive patterns, artificial grain, and uniformly sharp surfaces.

Apply material-specific guidance only when the material is present: skin should have irregular pores and subtle creases with naturally smooth intervals; hair should form coherent strands and groups, with only selective flyaways; irises should preserve source color, plausible internal structure, and restrained reflections; fabrics should maintain their original weave direction, scale, and motifs. Keep text, logos, facial features, and rigid shapes faithful to the source. When they are too blurred to verify, do not invent precise lettering or defining traits.

More detail is not automatically better. Prefer believable local contrast, clean boundaries, and coherent textures over aggressive sharpening or fabricated microdetail. Preserve blur that belongs to the original depth of field or intentional motion rather than making every area equally crisp.

## 3. Registration, blending, and quality control

Map each edited crop back to its saved source coordinates. Start with **global similarity registration** to align scale, rotation, and position. Apply only bounded, smooth local corrections when correspondences are reliable; never bend rigid geometry or repeated patterns to force alignment. If registration cannot be trusted, retain the pixels from the previous full-image result rather than inserting a mismatched patch.

Match broad exposure and color before compositing without copying old fine texture over the new detail. Blend overlaps using normalized weights or multiband blending. Feather approximately **15–25% of the crop border**, tapering the patch contribution toward zero at internal boundaries to prevent visible seams. Keep native edited crops and intermediate full-image results so individual defects can be corrected without repeating the entire process.

**After each pass**, inspect the full image and representative focal areas and overlaps at **100% display scale**. Check for doubled features, registration drift, seams, inconsistent texture, changes to identity, distorted shapes, invented marks, and excessive sharpening. Make up to **two targeted retries per defect**; if a correction still fails, revert that region to the prior reliable result and disclose the limitation. Do not silently accept a visually striking but inaccurate edit.

## 4. Final export and delivery

Export the final assembled result as a **lossless PNG at exactly the original width and height**. Do not increase pixel dimensions, crop away content, stretch the image, or change its aspect ratio. Verify that the file decodes correctly and that its measured dimensions match the source. Inspect the actual exported image, not just intermediate previews.

Deliver the final image and a preview, along with the number of refinement passes, relevant settings, and editing prompts. Briefly identify which visible qualities improved and note any unresolved defects or uncertain reconstructed details. Describe the outcome as **visual quality enhancement at the original resolution**, not true 4K/8K upscaling or guaranteed recovery of information absent from the source.
