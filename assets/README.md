# UpscalingByNetwork Assets

This directory contains the required binary executables and models for the UpscalingByNetwork project.

## Directory Structure

```
assets/
├── ffmpeg/           # FFmpeg binary executables
│   ├── windows/      # Windows binaries
│   │   └── x64/      # 64-bit Windows executables
│   └── linux/        # Linux binaries
│       └── x64/      # 64-bit Linux executables
├── realesrgan/       # Real-ESRGAN binary executables
│   ├── windows/      # Windows binaries
│   │   └── x64/      # 64-bit Windows executables
│   └── linux/        # Linux binaries
│       └── x64/      # 64-bit Linux executables
└── models/           # AI upscaling models
```

## Overview

The assets directory is organized by tool and platform to ensure proper binary distribution and cross-platform compatibility. All binaries are architecture-specific and organized in a consistent structure.

## Platform Support

### Currently Supported
- **Windows**: x64 (64-bit)
- **Linux**: x64 (64-bit)

### Architecture Support
All platforms currently support x64 architecture. Future support for ARM architectures may be added.

## Adding New Binaries

### For FFmpeg
1. Download the appropriate FFmpeg build for your platform from the official sources
2. Place the executable in the corresponding platform/architecture directory
3. Ensure the executable has proper permissions (chmod +x on Linux)
4. Update the FFmpeg README.md with version information

### For Real-ESRGAN
1. Download the Real-ESRGAN ncnn Vulkan binaries from the GitHub releases
2. Place all executables and required libraries in the corresponding directory
3. On Windows, ensure all required DLLs are included
4. Update the Real-ESRGAN README.md with version information

### For Models
1. Download the model files (.pth or .bin format) from official sources
2. Place the model files in the `models/` directory
3. Update the models README.md with model information and descriptions
4. Ensure model filenames are descriptive and include version/type information

## License Information

This directory contains third-party binaries and models with different licenses:

- **FFmpeg**: Licensed under LGPL 2.1+ or GPL 2+ depending on build configuration
  - See `ffmpeg/README.md` for details
- **Real-ESRGAN**: Licensed under BSD-3-Clause License
  - See `realesrgan/README.md` for details
- **Models**: Various licenses depending on the model source
  - See `models/README.md` for individual model licenses

## Important Notes

1. **Binary Distribution**: Binaries are not included in the main repository due to size constraints. They must be downloaded separately.
2. **Version Management**: Always document the version of binaries and models you add.
3. **Security**: Only download binaries from official and trusted sources.
4. **Updates**: Regularly check for updates to binaries and models to ensure optimal performance and security.

## Getting Started

For initial setup, refer to the README files in each subdirectory for download links and installation instructions:

- [FFmpeg Setup](ffmpeg/README.md)
- [Real-ESRGAN Setup](realesrgan/README.md)
- [Models Setup](models/README.md)

## Directory Size Expectations

- FFmpeg binaries: ~50-100 MB per platform
- Real-ESRGAN binaries: ~20-50 MB per platform
- Models: ~5-200 MB per model (varies by model type and size)

Total expected size: 500 MB - 2 GB depending on the number of models included.
