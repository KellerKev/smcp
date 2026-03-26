# SMCP Demo Recording

## Viewing the Demo

### Option 1: Local Playback
```bash
# Install asciinema
pip install asciinema  # or use your package manager

# Play the recording
asciinema play smcp_demo.cast
```

### Option 2: Upload to asciinema.org
```bash
# Upload (creates a shareable link)
asciinema upload smcp_demo.cast

# You'll get a URL like: https://asciinema.org/a/XXXXXX
```

### Option 3: Convert to GIF
```bash
# Install agg (asciinema gif generator)
pip install asciinema-agg

# Convert to GIF
agg smcp_demo.cast smcp_demo.gif
```

### Option 4: Embed in README
Add this to your README after uploading:
```markdown
[![asciicast](https://asciinema.org/a/XXXXXX.svg)](https://asciinema.org/a/XXXXXX)
```

## What the Demo Shows

1. **Security Modes**: Four different security levels from simple API keys to enterprise OAuth2
2. **Multi-Agent System**: Starting registry and multiple specialized agents
3. **Task Orchestration**: Distributing a complex task across multiple agents
4. **Performance**: Sub-4-second execution for multi-agent coordination
5. **Key Features**: MCP compatibility with added security and coordination

## Recording a New Demo

To record your own demo:
```bash
# Start recording
asciinema rec -t "Your Title" demo.cast

# Run your commands...

# Stop recording with Ctrl-D or exit

# Play it back
asciinema play demo.cast
```

## Sharing on LinkedIn

After uploading to asciinema.org or converting to GIF:

1. **With asciinema link**: Share the URL in your post
2. **With GIF**: Upload the GIF directly to LinkedIn
3. **Best practice**: Use a GIF for the feed, link to asciinema for full demo

## Demo Scripts

- `quick_demo.sh`: Fast 15-second demo showing key features
- `demo_script.sh`: Full 1-minute demo with animations
- Custom demos: Modify scripts to highlight specific features