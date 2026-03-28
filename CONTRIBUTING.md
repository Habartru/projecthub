# Contributing to ProjectHub

Thank you for your interest in contributing to ProjectHub! We welcome contributions from the community.

## How to Contribute

### Reporting Bugs

- Check if the bug has already been reported in [Issues](https://github.com/yourusername/projecthub/issues)
- If not, create a new issue with:
  - Clear title and description
  - Steps to reproduce
  - Expected vs actual behavior
  - Screenshots (if applicable)
  - System info (OS, Python version)

### Suggesting Features

- Open a [Discussion](https://github.com/yourusername/projecthub/discussions) first
- Describe the feature and its use case
- Wait for community feedback before implementing

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest` if available)
5. Commit with clear messages (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Style

- Python: Follow PEP 8
- JavaScript: Use consistent formatting
- HTML/CSS: Semantic markup, CSS variables for theming
- Add comments for complex logic
- Keep functions small and focused

### Adding Translations

1. Edit `backend/main.py`
2. Find `init_translations()` function
3. Add translations for all three languages (en, ru, zh)
4. Test in browser by switching languages

### Adding Themes

1. Edit `backend/static/index.html` and `settings.html`
2. Add CSS variables in `:root` and `[data-theme="your-theme"]`
3. Test all UI elements in the new theme
4. Update theme selector in settings

## Development Setup

```bash
git clone https://github.com/yourusername/projecthub.git
cd projecthub
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python backend/main.py
```

Visit `http://localhost:8472`

## Questions?

Join our [Discussions](https://github.com/yourusername/projecthub/discussions) or open an issue.

Thank you for making ProjectHub better! 🚀
