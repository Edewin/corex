# Building the Flatpak locally

```bash
flatpak install flathub org.kde.Sdk//6.10 io.qt.PySide.BaseApp//6.10
cd flatpak
flatpak-builder --user --install --force-clean build-dir io.github.edewin.corex.yml
flatpak run io.github.edewin.corex
```

The Flathub manifest is the same, with the `dir` source replaced by the release tag.
`generated-sources.json` comes from `flatpak-pip-generator --runtime org.kde.Sdk//6.10 pyqtgraph numpy nvidia-ml-py psutil`.
