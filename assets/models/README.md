# Real-ESRGAN Models

This directory contains AI upscaling models for use with Real-ESRGAN.

## Overview

Models are pre-trained neural networks that perform the actual upscaling. Different models are optimized for different types of content (anime, photos, general) and scaling factors (x2, x3, x4).

## Available Models

### 1. RealESRGAN_x4plus (General Purpose)

**Model Name**: `realesrgan-x4plus`

- **Use Case**: General photos and natural images
- **Scale Factor**: 4x upscaling
- **Best For**: Real-world photos, landscapes, portraits
- **File Size**: ~65 MB
- **Quality**: High quality for photographic content

**Files**:
- `realesrgan-x4plus.bin`
- `realesrgan-x4plus.param`

**Download**: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-x4plus.pth

### 2. RealESRGAN_x4plus_anime_6B (Anime/Illustrations)

**Model Name**: `realesrgan-x4plus-anime`

- **Use Case**: Anime, manga, illustrations, cartoons
- **Scale Factor**: 4x upscaling
- **Best For**: Hand-drawn art, anime screenshots, illustrations
- **File Size**: ~18 MB
- **Quality**: Optimized for preserving line art and anime-style content

**Files**:
- `realesrgan-x4plus-anime.bin`
- `realesrgan-x4plus-anime.param`

**Download**: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-x4plus-anime.pth

### 3. RealESRNet_x4plus (No-GAN Version)

**Model Name**: `realesrnet-x4plus`

- **Use Case**: Conservative upscaling without GAN artifacts
- **Scale Factor**: 4x upscaling
- **Best For**: When you want less aggressive enhancement
- **File Size**: ~65 MB
- **Quality**: More conservative, fewer potential artifacts

**Files**:
- `realesrnet-x4plus.bin`
- `realesrnet-x4plus.param`

**Download**: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.1/RealESRNet_x4plus.pth

### 4. RealESRGAN_x2plus (2x Upscaling)

**Model Name**: `realesrgan-x2plus`

- **Use Case**: Moderate upscaling for already high-quality images
- **Scale Factor**: 2x upscaling
- **Best For**: High-resolution sources that need slight enhancement
- **File Size**: ~65 MB
- **Quality**: Excellent for moderate upscaling needs

**Files**:
- `realesrgan-x2plus.bin`
- `realesrgan-x2plus.param`

**Download**: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth

## Model Comparison

| Model | Best For | Scale | Size | Speed | Detail |
|-------|----------|-------|------|-------|--------|
| realesrgan-x4plus | Photos | 4x | 65 MB | Medium | High |
| realesrgan-x4plus-anime | Anime/Art | 4x | 18 MB | Fast | High |
| realesrnet-x4plus | Conservative | 4x | 65 MB | Medium | Medium |
| realesrgan-x2plus | Light upscale | 2x | 65 MB | Fast | Medium |

## Download Instructions

### Method 1: Direct Download (Recommended)

Visit the official Real-ESRGAN releases page:
https://github.com/xinntao/Real-ESRGAN/releases

Download the `.pth` model files and place them in this directory.

### Method 2: Using wget/curl

**Linux/macOS**:
```bash
# Navigate to models directory
cd /DATA-2T/UpscalingByNetwork/assets/models

# Download RealESRGAN_x4plus (General)
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-x4plus.pth

# Download RealESRGAN_x4plus_anime
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-x4plus-anime.pth

# Download RealESRNet_x4plus
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.1/RealESRNet_x4plus.pth

# Download RealESRGAN_x2plus
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth
```

**Windows PowerShell**:
```powershell
# Navigate to models directory
cd C:\path\to\UpscalingByNetwork\assets\models

# Download models
Invoke-WebRequest -Uri "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-x4plus.pth" -OutFile "realesrgan-x4plus.pth"
Invoke-WebRequest -Uri "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-x4plus-anime.pth" -OutFile "realesrgan-x4plus-anime.pth"
```

## Model Format Conversion

Real-ESRGAN ncnn-vulkan requires models in `.bin` and `.param` format, not `.pth` format.

### Converting PyTorch Models to NCNN

The `.pth` files from GitHub are PyTorch models. For ncnn-vulkan, you need:

1. **Pre-converted models**: Download from Real-ESRGAN releases (look for ncnn models)
2. **Convert yourself**: Use the conversion tools in the Real-ESRGAN repository

**Note**: Most Real-ESRGAN ncnn-vulkan releases include the models in the correct format. Check the release assets for files ending in `.bin` and `.param`.

### Correct Download for NCNN

For ncnn-vulkan binaries, download models from:
https://github.com/xinntao/Real-ESRGAN/releases

Look for packages like:
- `realesrgan-ncnn-vulkan-{version}-windows.zip`
- `realesrgan-ncnn-vulkan-{version}-ubuntu.zip`

These packages include the models in the correct `.bin`/`.param` format.

## Usage Recommendations

### For Video Upscaling

1. **Anime/Cartoons**: Use `realesrgan-x4plus-anime`
   - Best quality for animated content
   - Fastest processing
   - Preserves line art and flat colors

2. **Live Action**: Use `realesrgan-x4plus`
   - Best for real-world footage
   - Good detail preservation
   - Natural-looking results

3. **Mixed Content**: Test both models on sample frames
   - Compare quality and artifacts
   - Choose based on visual preference

### For Different Input Resolutions

- **SD (480p → 1080p/4K)**: Use 4x models
- **HD (720p → 1440p)**: Use 2x model
- **Full HD (1080p → 4K)**: Use 2x model
- **Low quality sources**: Use 4x model with caution (may amplify compression artifacts)

### Quality vs Performance Trade-offs

1. **Best Quality**: `realesrgan-x4plus` (photos) or `realesrgan-x4plus-anime` (anime)
2. **Balanced**: `realesrgan-x2plus` (when 4x is overkill)
3. **Conservative**: `realesrnet-x4plus` (minimal enhancement)

## Model File Structure

Each model consists of two files:

1. **`.param` file**: Network structure and layer definitions
2. **`.bin` file**: Trained weights and parameters

Both files must be present and have matching names for the model to load.

## Storage Requirements

### Minimum Setup (One Model)
- Single model: ~18-65 MB
- Total: ~20-70 MB

### Recommended Setup (All Models)
- 4 models × ~65 MB average
- Total: ~200-260 MB

### Full Setup (All Variants)
- All available models
- Total: ~300-500 MB

## License Information

### Model Licenses

Real-ESRGAN models are released under the **BSD 3-Clause License**.

**Key Points**:
- Free for commercial and non-commercial use
- Modification and redistribution allowed
- Attribution required
- No warranty provided

### Training Data

Models are trained on various datasets:
- **DF2K**: DIV2K + Flickr2K datasets
- **OST**: Outdoor Scene Training dataset
- **Custom datasets**: For anime-specific models

### Citation

If using Real-ESRGAN in academic work, cite:

```bibtex
@InProceedings{wang2021realesrgan,
    author    = {Xintao Wang and Liangbin Xie and Chao Dong and Ying Shan},
    title     = {Real-ESRGAN: Training Real-World Blind Super-Resolution with Pure Synthetic Data},
    booktitle = {International Conference on Computer Vision Workshops (ICCVW)},
    date      = {2021}
}
```

## Troubleshooting

### Model Not Found

1. Verify both `.bin` and `.param` files exist
2. Check file naming matches exactly (case-sensitive on Linux)
3. Ensure files are not corrupted (check file sizes)

### Poor Quality Results

1. **Wrong model for content type**:
   - Use anime model for anime content
   - Use general model for photos

2. **Input too low quality**:
   - Heavily compressed sources may produce artifacts
   - Try conservative model (realesrnet-x4plus)

3. **Scaling factor mismatch**:
   - Use appropriate scale for input resolution
   - Don't over-upscale low-quality sources

### Memory Issues

1. Models load into GPU memory
2. Larger models (65 MB) require more VRAM
3. Processing tile size also affects memory usage
4. If out of memory, reduce tile size in Real-ESRGAN settings

## Updates and New Models

Check for new model releases:
- GitHub Releases: https://github.com/xinntao/Real-ESRGAN/releases
- Model Zoo: https://github.com/xinntao/Real-ESRGAN/blob/master/docs/model_zoo.md

New models may include:
- Improved versions of existing models
- Specialized models for specific content types
- Models for different scale factors (3x, etc.)

## Additional Resources

- Real-ESRGAN Paper: https://arxiv.org/abs/2107.10833
- Model Zoo: https://github.com/xinntao/Real-ESRGAN/blob/master/docs/model_zoo.md
- Training Guide: https://github.com/xinntao/Real-ESRGAN/blob/master/docs/Training.md
- Inference Guide: https://github.com/xinntao/Real-ESRGAN/blob/master/docs/inference_tutorial.md

## Community Models

The community has created additional models:

1. **anime6B**: Enhanced anime model
2. **animevideo**: Optimized for anime video
3. **Custom trained**: Various specialized models

Check community resources and forums for additional models optimized for specific use cases.
