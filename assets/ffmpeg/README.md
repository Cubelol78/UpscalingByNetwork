# FFmpeg Binaries

This directory contains FFmpeg binary executables for different platforms.

## Version Information

**Recommended Version**: FFmpeg 6.0 or later

FFmpeg is used for video/audio processing, including:
- Video frame extraction
- Video encoding/decoding
- Audio stream handling
- Container format conversion
- Stream multiplexing

## Download Sources

### Official Sources

#### Windows (x64)
- **Official Builds**: https://www.gyan.dev/ffmpeg/builds/
  - Download: `ffmpeg-release-essentials.zip` or `ffmpeg-release-full.zip`
  - Extract `ffmpeg.exe`, `ffprobe.exe`, and `ffplay.exe` to `windows/x64/`
- **Alternative**: https://github.com/BtbN/FFmpeg-Builds/releases
  - Download: `ffmpeg-master-latest-win64-gpl.zip`

#### Linux (x64)
- **Official Static Builds**: https://johnvansickle.com/ffmpeg/
  - Download: `ffmpeg-release-amd64-static.tar.xz`
  - Extract `ffmpeg`, `ffprobe`, and `ffplay` to `linux/x64/`
- **Alternative**: https://github.com/BtbN/FFmpeg-Builds/releases
  - Download: `ffmpeg-master-latest-linux64-gpl.tar.xz`

### Build Configuration

For optimal compatibility, use builds with the following features:
- **GPL Build**: Includes more codecs and features
- **libx264**: H.264 encoding support
- **libx265**: H.265/HEVC encoding support
- **libvpx**: VP8/VP9 encoding support
- **libopus**: Opus audio codec
- **Hardware Acceleration**: NVENC, QSV, or VAAPI support when available

## Installation Instructions

### Windows
1. Download the appropriate build from the sources above
2. Extract the archive
3. Copy `ffmpeg.exe` to `windows/x64/`
4. Optionally copy `ffprobe.exe` and `ffplay.exe` for additional functionality

### Linux
1. Download the static build from the sources above
2. Extract the archive: `tar -xf ffmpeg-release-amd64-static.tar.xz`
3. Copy the `ffmpeg` binary to `linux/x64/`
4. Make executable: `chmod +x linux/x64/ffmpeg`
5. Optionally copy `ffprobe` and `ffplay`

## License Information

FFmpeg is licensed under the **GNU Lesser General Public License (LGPL) version 2.1** or later.

### Important License Notes

1. **GPL vs LGPL**:
   - Standard builds are LGPL 2.1+
   - Builds with GPL-only components (like libx264) are GPL 2+
   - Check your specific build's license

2. **Distribution Requirements**:
   - You must provide license and copyright information
   - Source code must be available for GPL builds
   - LGPL builds allow dynamic linking without GPL requirements

3. **Patent Considerations**:
   - Some codecs (H.264, H.265) may be subject to patent licensing
   - Ensure compliance with relevant patent pools (MPEG-LA, HEVC Advance)

### License Files

When distributing FFmpeg binaries, include:
- LICENSE.txt (from FFmpeg distribution)
- README.txt (build information)
- Link to FFmpeg source code: https://github.com/FFmpeg/FFmpeg

## Version Verification

To verify the installed version:

```bash
# Windows
.\windows\x64\ffmpeg.exe -version

# Linux
./linux/x64/ffmpeg -version
```

Expected output should include:
- FFmpeg version number
- Build configuration
- Enabled libraries and codecs

## Platform-Specific Notes

### Windows
- **Visual C++ Runtime**: Some builds may require Visual C++ Redistributable
- **Antivirus**: FFmpeg may be flagged by some antivirus software (false positive)
- **Path Spaces**: Ensure no spaces in path or use quotes when calling

### Linux
- **Static vs Dynamic**: Static builds are recommended for portability
- **Dependencies**: Static builds have no external dependencies
- **Permissions**: Ensure executable permissions are set (`chmod +x`)
- **glibc Version**: Check minimum glibc requirements for your distribution

### Performance Considerations

1. **Hardware Acceleration**:
   - Windows: NVENC (NVIDIA), QSV (Intel)
   - Linux: VAAPI (Intel/AMD), NVENC (NVIDIA)

2. **Multi-threading**: FFmpeg automatically uses multiple CPU cores

3. **Memory Usage**: Large videos may require significant RAM

## Troubleshooting

### Common Issues

1. **"Command not found" or "Not recognized"**:
   - Verify file exists and path is correct
   - Check executable permissions (Linux)

2. **Codec errors**:
   - Ensure you're using a full/GPL build with required codecs
   - Check FFmpeg build configuration with `-codecs` flag

3. **Performance issues**:
   - Enable hardware acceleration if available
   - Check CPU/memory usage during processing

## Updates

FFmpeg is actively developed. Check for updates regularly:
- Release notes: https://ffmpeg.org/download.html
- Changelog: https://github.com/FFmpeg/FFmpeg/blob/master/Changelog

## Additional Resources

- Official Documentation: https://ffmpeg.org/documentation.html
- Wiki: https://trac.ffmpeg.org/wiki
- Community Support: https://ffmpeg.org/contact.html
- Bug Reports: https://trac.ffmpeg.org/

## File Size

- Windows x64: ~60-120 MB (depending on build configuration)
- Linux x64: ~80-150 MB (static builds include all dependencies)
