# Forensiq Demo - Cognitive UI

*This documentation is licensed under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/) (CC BY-SA 4.0).*

This is the Forensiq demo referenced in the Thalamus whitepaper. It demonstrates a textual TUI (Terminal User Interface) representing cognitive AI layers.

## Overview

The Forensiq demo showcases the cognitive architecture described in the Thalamus whitepaper through an interactive terminal interface. It simulates the flow of information through different cognitive layers including:

- **Cochlea**: Raw sensory input processing
- **Thalamus**: Parallel refinement and flow control
- **Cerebellum**: Reflex processing and quick responses
- **Prime Agent**: Higher-order synthesis and decision-making

## Features

- Real-time cognitive layer visualization
- Interactive terminal interface
- Simulated data flow through cognitive architecture
- Demonstration of reflex vs. depth processing

## Requirements

```bash
pip install textual rich
```

## Usage

```bash
python main.py
```

## Architecture

The demo implements the cognitive architecture described in the Thalamus whitepaper:

1. **Raw Input Processing**: Simulates Cochlea receiving sensory data
2. **Parallel Refinement**: Shows Thalamus processing raw input while preparing refined versions
3. **Reflex Processing**: Demonstrates Cerebellum's quick response capabilities
4. **Deep Cognition**: Shows Prime Agent's higher-order processing

## Demo Modes

- **Interactive Mode**: User can interact with the interface
- **Test Mode**: Automated demonstration of the system
- **Auto-close Mode**: Runs demo and exits automatically

## Related Documentation

- [Thalamus Whitepaper](../../thalamus_whitepaper_draft%20(1).md) - Main technical documentation
- [Demo Guide](../DEMO_GUIDE.md) - General demo instructions
- [API Reference](../API_REFERENCE.md) - Technical API documentation
