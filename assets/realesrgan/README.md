# Real-ESRGAN Binaries

This directory contains Real-ESRGAN ncnn Vulkan binary executables for different platforms.

## Version Information

**Recommended Version**: Real-ESRGAN v0.2.5.0 or later

Real-ESRGAN (Real-World Enhanced Super-Resolution Generative Adversarial Network) is used for:
- AI-powered image upscaling
- Video frame upscaling (frame-by-frame)
- Noise reduction and detail enhancement
- Multiple model support for different use cases

## Download Sources

### Official GitHub Releases

**Repository**: https://github.com/xinntao/Real-ESRGAN

#### Windows (x64)
- **Release URL**: https://github.com/xinntao/Real-ESRGAN/releases
- **Package**: `realesrgan-ncnn-vulkan-{version}-windows.zip`
- **Required Files**:
  - `realesrgan-ncnn-vulkan.exe` - Main executable
  - `vcomp140.dll` - OpenMP runtime (if not using static build)
  - `vcomp140d.dll` - Debug version (optional)

**Installation**:
1. Download the latest Windows release
2. Extract all files from the archive
3. Copy all `.exe` and `.dll` files to `windows/x64/`

#### Linux (x64)
- **Release URL**: https://github.com/xinntao/Real-ESRGAN/releases
- **Package**: `realesrgan-ncnn-vulkan-{version}-ubuntu.zip`
- **Required Files**:
  - `realesrgan-ncnn-vulkan` - Main executable

**Installation**:
1. Download the latest Ubuntu/Linux release
2. Extract the archive
3. Copy `realesrgan-ncnn-vulkan` to `linux/x64/`
4. Make executable: `chmod +x linux/x64/realesrgan-ncnn-vulkan`

## License Information

Real-ESRGAN is licensed under the **BSD 3-Clause License**.

### License Summary

```
BSD 3-Clause License

Copyright (c) 2021, Xintao Wang
All rights reserved.
```

### Key Points

1. **Permissive License**: Free for commercial and non-commercial use
2. **Modification Allowed**: Can modify and redistribute
3. **Attribution Required**: Must include copyright notice and license text
4. **No Warranty**: Provided "as is" without warranty

### Full License

The full license text is available at:
- https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE

## Dependencies

### Windows Requirements
- **Vulkan Runtime**: Required for GPU acceleration
  - Download: https://vulkan.lunarg.com/sdk/home
  - Usually pre-installed with GPU drivers
- **Visual C++ Redistributable**: MSVC runtime libraries
  - Download: https://support.microsoft.com/en-us/help/2977003/the-latest-supported-visual-c-downloads
- **GPU**: NVIDIA, AMD, or Intel GPU with Vulkan support

### Linux Requirements
- **Vulkan Loader**: `libvulkan.so.1`
  - Ubuntu/Debian: `sudo apt install libvulkan1`
  - Fedora/RHEL: `sudo dnf install vulkan-loader`
  - Arch: `sudo pacman -S vulkan-icd-loader`
- **GPU Drivers**: Up-to-date drivers with Vulkan support
  - NVIDIA: Latest proprietary drivers
  - AMD: Mesa or AMDGPU-PRO drivers
  - Intel: Mesa drivers

## Platform-Specific Notes

### Windows
1. **DLL Dependencies**:
   - `vcomp140.dll` - OpenMP runtime (OpenMP support)
   - May require Visual C++ 2015-2022 Redistributable

2. **GPU Selection**:
   - Automatically selects the best available GPU
   - Use `-g` parameter to specify GPU (0, 1, 2, etc.)

3. **Antivirus**: May be flagged as suspicious (false positive)

### Linux
1. **Static vs Dynamic Build**:
   - Official releases are typically dynamically linked
   - Requires Vulkan loader to be installed

2. **GPU Permissions**:
   - Ensure user has access to GPU devices
   - May need to add user to `video` or `render` group

3. **Wayland/X11**: Works with both display servers

## Usage Examples

### Basic Upscaling

**Windows**:
```cmd
.\windows\x64\realesrgan-ncnn-vulkan.exe -i input.jpg -o output.jpg -n realesrgan-x4plus
```

**Linux**:
```bash
./linux/x64/realesrgan-ncnn-vulkan -i input.jpg -o output.jpg -n realesrgan-x4plus
```

### Common Parameters

- `-i <input>`: Input image path
- `-o <output>`: Output image path
- `-n <model>`: Model name (without .bin/.param extension)
- `-s <scale>`: Upscale ratio (2, 3, or 4)
- `-t <tile_size>`: Tile size (default: 0 = auto)
- `-g <gpu_id>`: GPU device to use (default: 0)
- `-j <threads>`: Thread count for load/save (default: 1:2:2)
- `-f <format>`: Output image format

## Model Compatibility

Real-ESRGAN requires model files to be present in the `models/` directory.

### Required Files Per Model

Each model requires two files:
1. `{model_name}.bin` - Model weights
2. `{model_name}.param` - Model parameters

### Model Loading

The executable looks for models in:
1. Same directory as executable
2. `./models/` subdirectory
3. Custom path specified with `-m` parameter

**Recommended**: Place all models in `/DATA-2T/UpscalingByNetwork/assets/models/`

## Verification

### Version Check

**Windows**:
```cmd
.\windows\x64\realesrgan-ncnn-vulkan.exe
```

**Linux**:
```bash
./linux/x64/realesrgan-ncnn-vulkan
```

Running without arguments shows version and usage information.

### GPU Check

Verify Vulkan support:

**Windows**:
```cmd
vulkaninfo
```

**Linux**:
```bash
vulkaninfo
```

Should list available Vulkan devices.

## Performance Considerations

1. **Tile Size**:
   - Larger tiles = faster processing but more VRAM
   - Default (auto) is usually optimal
   - Reduce if running out of GPU memory

2. **GPU Selection**:
   - Use integrated GPU for power saving
   - Use dedicated GPU for best performance

3. **Thread Count**:
   - Default settings are usually optimal
   - Adjust for CPU-bound systems

## Troubleshooting

### Common Issues

1. **"Vulkan is not supported" error**:
   - Install/update GPU drivers
   - Install Vulkan runtime (Windows) or loader (Linux)
   - Verify GPU supports Vulkan

2. **"Model not found" error**:
   - Ensure model files are in correct location
   - Check model name matches file name (without extension)
   - Verify both .bin and .param files exist

3. **Out of memory errors**:
   - Reduce tile size with `-t 256` or `-t 128`
   - Close other GPU-intensive applications
   - Use smaller scale factor if possible

4. **Performance issues**:
   - Ensure correct GPU is selected
   - Check GPU is not thermal throttling
   - Verify Vulkan drivers are up to date

### Linux-Specific Issues

1. **Permission denied**:
   - Run `chmod +x realesrgan-ncnn-vulkan`
   - Check user has GPU access

2. **Library not found**:
   - Install Vulkan loader: `sudo apt install libvulkan1`
   - Verify with `ldd realesrgan-ncnn-vulkan`

## Updates

Check for new releases regularly:
- GitHub Releases: https://github.com/xinntao/Real-ESRGAN/releases
- Changelog: Check release notes for improvements and bug fixes

## Additional Resources

- Official Repository: https://github.com/xinntao/Real-ESRGAN
- Documentation: https://github.com/xinntao/Real-ESRGAN/blob/master/README.md
- Paper: https://arxiv.org/abs/2107.10833
- ncnn Framework: https://github.com/Tencent/ncnn

## File Size

- Windows x64: ~15-30 MB (executable + DLLs)
- Linux x64: ~20-35 MB (executable)
