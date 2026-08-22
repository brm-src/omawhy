import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  readonly property string pluginId: "io.github.brm-src.omawhy"
  readonly property string helperPath: Qt.resolvedUrl("omawhy.py").toString().replace("file://", "")
  readonly property bool isSpanish: uiLanguage === "es"
  property string uiLanguage: Qt.locale().name.toLowerCase().startsWith("es") ? "es" : "en"
  property bool opened: false
  property string phase: "home" // home, scan, pick, inspect, confirm, shortcut, status
  property var selected: ({})
  property var explanation: ({})
  property var diagnostic: ({})
  property var scanResult: ({})
  property string status: ""
  property var processCallback: null

  function words(es, en) { return root.isSpanish ? es : en }

  function open() {
    root.opened = true
    root.phase = "home"
    root.selected = ({})
    root.explanation = ({})
    root.diagnostic = ({})
    root.scanResult = ({})
    root.status = root.words("¿Qué quieres entender?", "What do you want to understand?")
  }

  function close() {
    root.opened = false
    root.phase = "home"
    root.selected = ({})
    root.explanation = ({})
    root.diagnostic = ({})
    root.scanResult = ({})
    root.status = ""
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function runHelper(args, callback) {
    if (helper.running) return
    root.processCallback = callback
    helper.command = ["python3", root.helperPath].concat(args, ["--lang", root.uiLanguage])
    helper.running = true
  }

  function handlePayload(raw) {
    var payload
    try {
      payload = JSON.parse(String(raw || "{}"))
    } catch (error) {
      root.status = root.words("OmaWhy no pudo leer la respuesta del sistema.", "OmaWhy could not read the system response.")
      return
    }
    if (root.processCallback) root.processCallback(payload)
    root.processCallback = null
  }

  function loadExplanation() {
    root.status = root.words("Buscando reglas que coincidan…", "Looking for matching rules…")
    root.runHelper(["explain", "--window-json", JSON.stringify(root.selected)], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || root.words("No se pudieron analizar las reglas.", "Could not analyze the rules.")
        return
      }
      root.explanation = payload.explanation || ({})
      root.status = root.explanation.message || root.words("Análisis listo.", "Analysis ready.")
    })
  }

  function effectText(match) {
    var effects = match.effects || ({})
    var items = []
    if (effects.workspace) items.push("workspace " + effects.workspace)
    if (effects.monitor) items.push("monitor " + effects.monitor)
    if (effects.float !== undefined) items.push(root.words("flotante ", "floating ") + (effects.float ? root.words("sí", "yes") : root.words("no", "no")))
    if (effects.fullscreen !== undefined) items.push("fullscreen " + (effects.fullscreen ? root.words("sí", "yes") : root.words("no", "no")))
    if (effects.pin !== undefined) items.push(root.words("fijada ", "pinned ") + (effects.pin ? root.words("sí", "yes") : root.words("no", "no")))
    if (effects.opacity) items.push("opacidad " + effects.opacity)
    if (effects.tag) items.push("tag " + effects.tag)
    return items.length ? items.join(" · ") : root.words("regla coincidente", "matching rule")
  }

  function openMatchedRule(match) {
    root.runHelper(["open-rule", "--path", String(match.path || "")], function(payload) {
      root.status = payload.message || payload.error || root.words("Listo.", "Done.")
    })
  }

  function openShortcutSource() {
    var events = root.diagnostic.events || []
    var source = root.diagnostic.binding || (events.length ? events[events.length - 1] : ({}))
    if (source.path) root.openMatchedRule(source)
  }

  function startWindowQuestion() {
    root.phase = "pick"
    root.status = root.words("Haz clic sobre la ventana que quedó rara. Esc cancela.", "Click the window that looks wrong. Esc cancels.")
  }

  function inspectShortcut() {
    var keys = shortcutInput.text.trim()
    if (!keys) {
      root.status = root.words("Escribe un atajo, por ejemplo: Super Shift I.", "Type a shortcut, for example: Super Shift I.")
      return
    }
    root.status = root.words("Buscando ese atajo…", "Looking for that shortcut…")
    root.runHelper(["shortcut", "--keys", keys], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || root.words("No se pudo revisar el atajo.", "Could not check the shortcut.")
        return
      }
      root.diagnostic = payload.diagnosis || ({})
      root.status = root.diagnostic.message || root.words("Atajo revisado.", "Shortcut checked.")
    })
  }

  function inspectDesktop() {
    root.status = root.words("Revisando Hyprland, Quickshell y el atajo…", "Checking Hyprland, Quickshell, and the shortcut…")
    root.runHelper(["desktop-status"], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || root.words("No se pudo revisar el escritorio.", "Could not check the desktop.")
        return
      }
      root.diagnostic = payload.status || ({})
      root.status = root.diagnostic.message || root.words("Estado revisado.", "Status checked.")
    })
  }

  function runScan() {
    root.phase = "scan"
    root.scanResult = ({})
    root.status = root.words("Revisando configuración, atajos y procesos…", "Checking configuration, shortcuts, and processes…")
    root.runHelper(["scan"], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || root.words("No se pudo escanear el sistema.", "Could not scan the system.")
        return
      }
      root.scanResult = payload.scan || ({})
      root.status = root.scanResult.message || root.words("Escaneo listo.", "Scan done.")
    })
  }

  function runPerf() {
    root.phase = "scan"
    root.scanResult = ({})
    root.status = root.words("Midiendo CPU, memoria, temperatura, disco y batería…", "Measuring CPU, memory, temperature, disk, and battery…")
    root.runHelper(["perf"], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || root.words("No se pudieron tomar las mediciones.", "Could not take the measurements.")
        return
      }
      root.scanResult = payload.scan || ({})
      root.status = root.scanResult.message || root.words("Mediciones listas.", "Measurements done.")
    })
  }

  function openProblemSource(problem) {
    if (!problem.path) return
    root.runHelper(["open-rule", "--path", String(problem.path)], function(payload) {
      root.status = payload.message || payload.error || root.words("Listo.", "Done.")
    })
  }

  function severityLabel(severity) {
    if (severity === "error") return "ERROR"
    if (severity === "warning") return root.words("OJO", "WARN")
    return "INFO"
  }

  function copyDiagnostic() {
    var problems = root.scanResult.problems || []
    var lines = []
    lines.push("OmaWhy · " + root.words("revisión del sistema", "system review"))
    lines.push(root.scanResult.message || "")
    lines.push(root.words("Total", "Total") + ": " + String(root.scanResult.total || 0) +
      " (" + String(root.scanResult.summary ? root.scanResult.summary.error : 0) + " " + root.words("errores", "errors") +
      " · " + String(root.scanResult.summary ? root.scanResult.summary.warning : 0) + " " + root.words("avisos", "warnings") + ")")
    for (var i = 0; i < problems.length; i++) {
      var p = problems[i]
      lines.push("[" + root.severityLabel(p.severity) + "] " + String(p.title || ""))
      if (p.detail) lines.push("    " + String(p.detail))
      if (p.path) lines.push("    " + String(p.path) + (p.line ? ":" + String(p.line) : ""))
    }
    root.runHelper(["copy-stdin", "--text", lines.join("\n")], function(payload) {
      root.status = payload.message || payload.error || root.words("Copiado.", "Copied.")
    })
  }

  function inspectAtCursor() {
    root.status = root.words("Leyendo la ventana…", "Reading the window…")
    root.runHelper(["inspect-at-cursor"], function(payload) {
      if (!payload.ok) {
        root.status = payload.error || root.words("No se encontró una ventana.", "No window found.")
        return
      }
      root.selected = payload.window
      root.phase = "inspect"
      root.status = root.words("Ventana inspeccionada.", "Window inspected.")
      Qt.callLater(root.loadExplanation)
    })
  }

  function action(name) {
    if (name === "remember") {
      root.phase = "confirm"
      root.status = root.words("Revisa la regla antes de guardarla.", "Review the rule before saving it.")
      return
    }
    if (name === "undo" || name === "open-rules") {
      root.runHelper([name], function(payload) { root.status = payload.message || payload.error || root.words("Listo.", "Done.") })
      return
    }
    root.runHelper(["action", name, "--window-json", JSON.stringify(root.selected)], function(payload) {
      root.status = payload.message || payload.error || root.words("Listo.", "Done.")
    })
  }

  function saveRememberedRule() {
    root.runHelper(["remember", "--window-json", JSON.stringify(root.selected)], function(payload) {
      root.phase = "inspect"
      root.status = payload.message || payload.error || root.words("Listo.", "Done.")
    })
  }

  IpcHandler {
    target: root.pluginId
    function open(): string { root.open(); return "ok" }
    function close(): string { root.close(); return "ok" }
    function show(): string { root.open(); return "ok" }
    function hide(): string { root.close(); return "ok" }
    function toggle(): string { root.toggle(); return "ok" }
  }

  Process {
    id: helper
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handlePayload(text)
    }
  }

  component SectionHeader: Text {
    id: sectionHeaderText
    property string label: ""
    width: parent.width
    text: sectionHeaderText.label
    color: Color.accent
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.caption
    font.bold: true
    font.letterSpacing: 1.0
    elide: Text.ElideRight
  }

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: panel
      required property var modelData
      screen: modelData
      visible: root.opened
      anchors { top: true; bottom: true; left: true; right: true }
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.namespace: root.pluginId
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

      Keys.onEscapePressed: root.close()
      Keys.onPressed: function(event) {
        if (event.key === Qt.Key_W && (event.modifiers & Qt.MetaModifier)) {
          root.close()
          event.accepted = true
        }
      }

      Rectangle {
        anchors.fill: parent
        color: root.phase === "pick" ? Util.alpha(Color.background, 0.18) : Color.menu.scrim
        opacity: root.opened ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
      }

      MouseArea {
        anchors.fill: parent
        enabled: root.phase === "pick"
        cursorShape: Qt.CrossCursor
        onClicked: root.inspectAtCursor()
      }

      Rectangle {
        id: pickHint
        visible: root.phase === "pick"
        z: 2
        width: 390
        height: hintText.implicitHeight + 32
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: Color.menu.background
        border.width: 0
        scale: 1
        opacity: 1
        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onVisibleChanged: { if (visible) { scale = 0.96; opacity = 0; Qt.callLater(function() { scale = 1; opacity = 1 }) } }

        Text {
          id: hintText
          anchors.fill: parent
          anchors.margins: 16
          text: "OMAWHY\n" + root.words("Haz clic sobre una ventana para entender por qué está ahí.", "Click a window to understand why it is there.") + "\n\n" + root.words("Esc para cancelar", "Esc to cancel")
          color: Color.menu.text
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.body
          lineHeight: 1.25
          wrapMode: Text.Wrap
          textFormat: Text.PlainText
        }
      }

      Rectangle {
        id: homeCard
        visible: root.phase === "home"
        z: 3
        width: Math.min(540, parent.width - 36)
        height: homeContent.implicitHeight + 34
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: Color.menu.background
        border.width: 0
        scale: 1
        opacity: 1
        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onVisibleChanged: { if (visible) { scale = 0.96; opacity = 0; Qt.callLater(function() { scale = 1; opacity = 1 }) } }

        Column {
          id: homeContent
          anchors.fill: parent
          anchors.margins: 17
          spacing: 11
          Text {
            text: "OMAWHY"
            color: Color.accent
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
            font.bold: true
            font.letterSpacing: 1.5
          }
          Text {
            width: parent.width
            text: root.words("¿Por qué Omarchy?", "Why Omarchy?")
            color: Color.menu.text
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Text {
            width: parent.width
            text: root.words("OmaWhy revisa tu configuración y procesos reales y explica el porqué. Solo reporta lo que puede evidenciar; no inventa causas.", "OmaWhy inspects your actual configuration and processes and explains why. It only reports what it can verify; it never invents causes.")
            color: Util.alpha(Color.menu.text, 0.70)
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
            wrapMode: Text.Wrap
          }

          Rectangle {
            width: homeContent.width
            height: scanOptionContent.implicitHeight + 18
            radius: Style.cornerRadius
            color: scanOptionMouse.containsMouse ? Style.selectedFillFor(Color.menu.text, Color.accent) : Style.normalFillFor(Color.menu.text, Color.accent)
            border.width: 1
            border.color: Util.alpha(Color.accent, 0.55)
            Column {
              id: scanOptionContent
              anchors.fill: parent
              anchors.margins: 10
              spacing: 3
              Text { text: root.words("Revisar el sistema completo", "Scan the whole system"); color: Color.menu.text; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; font.bold: true }
              Text { width: parent.width; text: root.words("Busca atajos rotos, ejecutables inexistentes, fuentes perdidas y reglas inválidas.", "Finds broken shortcuts, missing executables, lost sources, and invalid rules."); color: Util.alpha(Color.menu.text, 0.68); font.family: Style.font.menuFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.Wrap }
            }
            MouseArea {
              id: scanOptionMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.runScan()
            }
          }

          Rectangle {
            width: homeContent.width
            height: perfOptionContent.implicitHeight + 18
            radius: Style.cornerRadius
            color: perfOptionMouse.containsMouse ? Style.selectedFillFor(Color.menu.text, Color.accent) : Style.normalFillFor(Color.menu.text, Color.accent)
            border.width: 1
            border.color: Util.alpha(Color.accent, 0.55)
            Column {
              id: perfOptionContent
              anchors.fill: parent
              anchors.margins: 10
              spacing: 3
              Text { text: root.words("¿Por qué va lento o está caliente?", "Why is it slow or hot?"); color: Color.menu.text; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; font.bold: true }
              Text { width: parent.width; text: root.words("Mide CPU, memoria, temperatura, disco y batería, y nombra a los culpables con evidencia.", "Measures CPU, memory, temperature, disk, and battery, and names the culprits with evidence."); color: Util.alpha(Color.menu.text, 0.68); font.family: Style.font.menuFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.Wrap }
            }
            MouseArea {
              id: perfOptionMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.runPerf()
            }
          }

          Text {
            width: parent.width
            text: root.words("O pregúntale por algo puntual:", "Or ask about something specific:")
            color: Util.alpha(Color.menu.text, 0.75)
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
            font.bold: true
          }

          Repeater {
            model: [
              [root.words("Una ventana quedó mal", "A window looks wrong"), root.words("¿Por qué abrió aquí, en este monitor o workspace?", "Why did it open here, on this monitor or workspace?"), "window"],
              [root.words("Un atajo no funciona", "A shortcut does not work"), root.words("Busca dónde está definido, reemplazado o desactivado.", "Finds where it is defined, replaced, or disabled."), "shortcut"],
              [root.words("Revisar estado del escritorio", "Check desktop status"), root.words("Comprueba Hyprland, Quickshell y el atajo de OmaWhy.", "Checks Hyprland, Quickshell, and the OmaWhy shortcut."), "status"]
            ]
            delegate: Rectangle {
              width: homeContent.width
              height: optionContent.implicitHeight + 20
              radius: Style.cornerRadius
              color: optionMouse.containsMouse ? Style.hoverFillFor(Color.menu.text, Color.accent) : Style.normalFillFor(Color.menu.text, Color.accent)
              border.width: 0
              Column {
                id: optionContent
                anchors.fill: parent
                anchors.margins: 10
                spacing: 3
                Text { text: modelData[0]; color: Color.menu.text; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; font.bold: true }
                Text { width: parent.width; text: modelData[1]; color: Util.alpha(Color.menu.text, 0.68); font.family: Style.font.menuFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.Wrap }
              }
              MouseArea {
                id: optionMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                  if (modelData[2] === "window") root.startWindowQuestion()
                  else if (modelData[2] === "shortcut") { root.phase = "shortcut"; root.diagnostic = ({}) }
                  else { root.phase = "status"; root.diagnostic = ({}); root.inspectDesktop() }
                }
              }
            }
          }
        }
      }

      Rectangle {
        id: scanCard
        visible: root.phase === "scan"
        z: 3
        width: Math.min(600, parent.width - 36)
        height: Math.min(scanContent.implicitHeight + 34, parent.height - 36)
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: Color.menu.background
        border.width: 0
        scale: 1
        opacity: 1
        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onVisibleChanged: { if (visible) { scale = 0.96; opacity = 0; Qt.callLater(function() { scale = 1; opacity = 1 }) } }

        Flickable {
          anchors.fill: parent
          anchors.margins: 17
          contentWidth: width
          contentHeight: scanContent.implicitHeight
          clip: true

          Column {
            id: scanContent
            width: parent.width
            spacing: 10
            Text { text: "OMAWHY"; color: Color.accent; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; font.bold: true; font.letterSpacing: 1.5 }
            Text {
              width: parent.width
              text: root.words("Revisión del sistema", "System review")
              color: Color.menu.text
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.title
              font.bold: true
              wrapMode: Text.Wrap
            }
            Text {
              width: parent.width
              text: root.status
              color: Util.alpha(Color.menu.text, 0.70)
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.Wrap
            }
            Rectangle {
              visible: root.scanResult.total !== undefined
              width: parent.width
              height: summaryText.implicitHeight + 18
              radius: 9
              color: root.scanResult.total > 0 ? Util.alpha(Color.accent, 0.16) : Util.alpha(Color.accent, 0.12)
              border.width: 1
              border.color: Util.alpha(Color.accent, 0.6)
              Text {
                id: summaryText
                anchors.fill: parent
                anchors.margins: 9
                text: root.scanResult.total > 0
                  ? (root.scanResult.summary.error || 0) + " " + root.words("errores", "errors") + " · " + (root.scanResult.summary.warning || 0) + " " + root.words("avisos", "warnings")
                  : root.words("Todo en orden. No encontré problemas evidentes.", "All good. I found no obvious problems.")
                color: Color.menu.text
                font.family: Style.font.menuFamily
                font.pixelSize: Style.font.body
                font.bold: true
                wrapMode: Text.Wrap
              }
            }
            Repeater {
              visible: root.scanResult.problems !== undefined
              model: root.scanResult.problems || []
              delegate: Rectangle {
                width: scanContent.width
                height: problemColumn.implicitHeight + 16
                radius: 8
                color: modelData.severity === "error"
                  ? Util.alpha(Color.urgent, 0.20)
                  : Util.alpha(Color.menu.text, 0.08)
                border.width: 1
                border.color: modelData.severity === "error"
                  ? Util.alpha(Color.urgent, 0.6)
                  : Util.alpha(Color.menu.text, 0.16)
                Column {
                  id: problemColumn
                  anchors.fill: parent
                  anchors.margins: 9
                  spacing: 4
                  Text {
                    width: parent.width
                    text: (modelData.severity === "error" ? "ERROR · " : root.words("OJO", "WARN") + " · ") + modelData.title
                    color: modelData.severity === "error" ? Color.urgent : Color.accent
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                    wrapMode: Text.Wrap
                  }
                  Text {
                    width: parent.width
                    text: String(modelData.detail || "")
                    color: Color.menu.text
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                  }
                  Text {
                    visible: modelData.path
                    width: parent.width
                    text: (String(modelData.path || "").split("/").pop() || "") + (modelData.line ? ":" + modelData.line : "") + "  ·  " + root.words("abrir archivo", "open file")
                    color: Util.alpha(Color.menu.text, 0.65)
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.caption
                    font.underline: problemSourceMouse.containsMouse
                    MouseArea {
                      id: problemSourceMouse
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: root.openProblemSource(modelData)
                    }
                  }
                }
              }
            }
            Row {
              width: parent.width
              spacing: Style.spacing.sm
              Button {
                id: scanAgain
                text: root.words("Escanear otra vez", "Scan again")
                bordered: true
                fontFamily: Style.font.menuFamily
                onClicked: root.runScan()
              }
              Button {
                id: copyDiagnosticButton
                text: root.words("Copiar diagnóstico", "Copy report")
                bordered: true
                fontFamily: Style.font.menuFamily
                enabled: root.scanResult.total !== undefined
                tooltipText: root.words("Copia el resumen y los problemas al portapapeles.", "Copies the summary and problems to the clipboard.")
                onClicked: root.copyDiagnostic()
              }
              Item { width: parent.width - scanAgain.width - copyDiagnosticButton.width - parent.spacing * 2; height: 1 }
              Button {
                text: root.words("Volver", "Back")
                fontFamily: Style.font.menuFamily
                onClicked: root.open()
              }
            }
          }
        }
      }

      Rectangle {
        id: card
        visible: (root.phase === "inspect" || root.phase === "confirm") && (!root.selected.monitor || modelData.name === root.selected.monitor)
        z: 3
        width: Math.min(560, parent.width - 36)
        height: Math.min(content.implicitHeight + 34, parent.height - 36)
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: Color.menu.background
        border.width: 0
        scale: 1
        opacity: 1
        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onVisibleChanged: { if (visible) { scale = 0.96; opacity = 0; Qt.callLater(function() { scale = 1; opacity = 1 }) } }

        Flickable {
          anchors.fill: parent
          anchors.margins: 17
          contentWidth: width
          contentHeight: content.implicitHeight
          clip: true

          Column {
            id: content
            width: parent.width
            spacing: 9

            Text {
              width: parent.width
              text: root.phase === "confirm" ? root.words("RECORDAR ESTA POSICIÓN", "REMEMBER THIS POSITION") : "OMAWHY"
              color: Color.accent
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              font.bold: true
              font.letterSpacing: 1.5
            }

            Text {
              width: parent.width
              text: String(root.selected.title || root.words("Ventana sin título", "Window without title"))
              color: Color.menu.text
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
            }

            Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.menu.text, 0.18) }

            Repeater {
              model: [
                [root.words("Class", "Class"), root.selected.identifier_kind === "class" ? "Class" : "App ID", root.selected.identifier],
                [root.words("Título", "Title"), root.selected.title],
                [root.words("Workspace", "Workspace"), root.selected.workspace],
                [root.words("Monitor", "Monitor"), root.selected.monitor],
                [root.words("Flotante", "Floating"), root.selected.floating ? root.words("sí", "yes") : root.words("no", "no")],
                [root.words("Pantalla completa", "Fullscreen"), root.selected.fullscreen ? root.words("sí", "yes") : root.words("no", "no")],
                [root.words("Fijada", "Pinned"), root.selected.pinned ? root.words("sí", "yes") : root.words("no", "no")],
                [root.words("PID", "PID"), root.selected.pid],
                [root.words("Dirección", "Address"), root.selected.address]
              ]
              delegate: Row {
                width: content.width
                spacing: 12
                Text {
                  width: 145
                  text: modelData[0]
                  color: Util.alpha(Color.menu.text, 0.58)
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.body
                }
                Text {
                  width: parent.width - 157
                  text: String(modelData[1] || "—")
                  color: Color.menu.text
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                }
              }
            }

            Rectangle {
              visible: root.phase === "inspect" && root.explanation.verdict !== undefined
              width: parent.width
              height: whyColumn.implicitHeight + 22
              radius: 9
              color: root.explanation.verdict === "placement-rule"
                ? Util.alpha(Color.accent, 0.18)
                : Util.alpha(Color.menu.text, 0.08)
              border.width: 1
              border.color: root.explanation.verdict === "placement-rule"
                ? Util.alpha(Color.accent, 0.75)
                : Util.alpha(Color.menu.text, 0.18)

              Column {
                id: whyColumn
                anchors.fill: parent
                anchors.margins: 11
                spacing: 7
                Text {
                  text: root.explanation.verdict === "placement-rule"
                    ? "ESTO PUEDE EXPLICAR DÓNDE QUEDÓ"
                    : root.explanation.verdict === "style-rule"
                      ? "HAY REGLAS, PERO NO MUEVEN LA VENTANA"
                      : "NO HAY REGLA ESTÁTICA COINCIDENTE"
                  color: root.explanation.verdict === "placement-rule" ? Color.accent : Color.menu.text
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                  font.letterSpacing: 1
                }
                Text {
                  width: parent.width
                  text: root.explanation.message || ""
                  color: Color.menu.text
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.body
                  wrapMode: Text.Wrap
                  textFormat: Text.PlainText
                }
              }
            }

            Repeater {
              visible: root.phase === "inspect"
              model: root.explanation.matches || []
              delegate: Rectangle {
                width: content.width
                height: sourceColumn.implicitHeight + 18
                radius: 8
                color: Util.alpha(Color.menu.text, 0.06)
                Column {
                  id: sourceColumn
                  anchors.fill: parent
                  anchors.margins: 9
                  spacing: 4
                  Text {
                    width: parent.width
                    text: String(modelData.path || "").split("/").pop() + ":" + modelData.line + " · " + root.effectText(modelData)
                    color: Color.accent
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.bodySmall
                    elide: Text.ElideRight
                  }
                  Text {
                    width: parent.width
                    text: modelData.rule || ""
                    color: Util.alpha(Color.menu.text, 0.70)
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                  Text {
                    text: root.words("Abrir archivo", "Open file")
                    color: Color.menu.text
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.bodySmall
                    font.underline: sourceMouse.containsMouse
                    MouseArea {
                      id: sourceMouse
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: root.openMatchedRule(modelData)
                    }
                  }
                }
              }
            }

            Text {
              visible: root.phase === "confirm"
              width: parent.width
              text: root.words("Se escribirá una regla limitada a esta aplicación en la configuración activa de Hyprland. OmaWhy crea un backup y puedes deshacer el último cambio.", "A scoped rule will be written for this application in the active Hyprland config. OmaWhy creates a backup and you can undo the last change.")
              wrapMode: Text.Wrap
              textFormat: Text.PlainText
              color: Util.alpha(Color.menu.text, 0.72)
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              lineHeight: 1.2
            }

            Column {
              visible: root.phase === "inspect"
              width: parent.width
              spacing: Style.spacing.xs

              SectionHeader { label: root.words("COPIAR", "COPY") }

              Flow {
                width: parent.width
                spacing: Style.spacing.sm
                Repeater {
                  model: [
                    [root.words("App ID", "App ID"), "copy-app-id"], [root.words("Class", "Class"), "copy-class"], [root.words("Título", "Title"), "copy-title"], [root.words("Regla", "Rule"), "copy-rule"]
                  ]
                  delegate: Button {
                    required property var modelData
                    text: modelData[0]
                    bordered: true
                    fontFamily: Style.font.menuFamily
                    onClicked: root.action(modelData[1])
                  }
                }
              }
              PanelSeparator { foreground: Color.menu.text }
              SectionHeader { label: root.words("VENTANA", "WINDOW") }
              Flow {
                width: parent.width
                spacing: Style.spacing.sm
                Repeater {
                  model: [
                    [root.words("Mover aquí", "Move here"), "move-current"], [root.words("Centrar", "Center"), "center"],
                    [root.words("Flotante", "Floating"), "toggle-floating"], [root.words("Pantalla completa", "Fullscreen"), "toggle-fullscreen"], [root.words("Fijar", "Pin"), "toggle-pin"]
                  ]
                  delegate: Button {
                    required property var modelData
                    text: modelData[0]
                    bordered: true
                    fontFamily: Style.font.menuFamily
                    onClicked: root.action(modelData[1])
                  }
                }
              }
              PanelSeparator { foreground: Color.menu.text }
              SectionHeader { label: root.words("REGLAS", "RULES") }
              Flow {
                width: parent.width
                spacing: Style.spacing.sm
                Repeater {
                  model: [
                    [root.words("Abrir reglas", "Open rules"), "open-rules"], [root.words("Recordar posición", "Remember position"), "remember"], [root.words("Deshacer", "Undo"), "undo"]
                  ]
                  delegate: Button {
                    required property var modelData
                    text: modelData[0]
                    bordered: true
                    fontFamily: Style.font.menuFamily
                    onClicked: root.action(modelData[1])
                  }
                }
              }
            }

            Row {
              visible: root.phase === "confirm"
              width: parent.width
              spacing: Style.spacing.sm
              Button {
                text: root.words("Recordar", "Remember")
                fontFamily: Style.font.menuFamily
                background: Color.accent
                foreground: Color.background
                accent: Color.accent
                onClicked: root.saveRememberedRule()
              }
              Button {
                text: root.words("Cancelar", "Cancel")
                bordered: true
                fontFamily: Style.font.menuFamily
                onClicked: root.phase = "inspect"
              }
            }

            Text {
              width: parent.width
              text: root.status
              color: Util.alpha(Color.menu.text, 0.65)
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.Wrap
              textFormat: Text.PlainText
            }
          }
        }
      }

      Rectangle {
        id: diagnosticCard
        visible: root.phase === "shortcut" || root.phase === "status"
        z: 3
        width: Math.min(520, parent.width - 36)
        height: Math.min(diagnosticContent.implicitHeight + 34, parent.height - 36)
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: Color.menu.background
        border.width: 0
        scale: 1
        opacity: 1
        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onVisibleChanged: { if (visible) { scale = 0.96; opacity = 0; Qt.callLater(function() { scale = 1; opacity = 1 }) } }

        Flickable {
          anchors.fill: parent
          anchors.margins: 17
          contentWidth: width
          contentHeight: diagnosticContent.implicitHeight
          clip: true
          Column {
            id: diagnosticContent
            width: parent.width
            spacing: 10
            Text { text: "OMAWHY"; color: Color.accent; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; font.bold: true; font.letterSpacing: 1.5 }
            Text {
              width: parent.width
              text: root.phase === "shortcut" ? "¿Por qué no funciona este atajo?" : "¿Está sano el escritorio?"
              color: Color.menu.text
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.title
              font.bold: true
              wrapMode: Text.Wrap
            }
            Text {
              visible: root.phase === "shortcut"
              width: parent.width
              text: root.words("Escríbelo como lo presionas: Super Shift I, Super Return, etc.", "Write it as you press it: Super Shift I, Super Return, etc.")
              color: Util.alpha(Color.menu.text, 0.68)
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.Wrap
            }
            TextField {
              id: shortcutInput
              visible: root.phase === "shortcut"
              width: parent.width
              placeholderText: root.words("Ejemplo: Super Shift I", "Example: Super Shift I")
              onAccepted: root.inspectShortcut()
            }
            Button {
              visible: root.phase === "shortcut"
              text: root.words("Revisar", "Check")
              fontFamily: Style.font.menuFamily
              background: Color.accent
              foreground: Color.background
              accent: Color.accent
              onClicked: root.inspectShortcut()
            }
            Text {
              visible: root.phase === "status"
              width: parent.width
              text: root.words("Esto revisa si la configuración activa existe, si Hyprland y Quickshell responden, y si el atajo de OmaWhy está definido.", "This checks whether the active config exists, whether Hyprland and Quickshell respond, and whether the OmaWhy shortcut is defined.")
              color: Util.alpha(Color.menu.text, 0.68)
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.Wrap
            }
            Button {
              visible: root.phase === "status"
              text: root.words("Revisar otra vez", "Check again")
              fontFamily: Style.font.menuFamily
              background: Color.accent
              foreground: Color.background
              accent: Color.accent
              onClicked: root.inspectDesktop()
            }
            Rectangle {
              visible: root.diagnostic.message !== undefined
              width: parent.width
              height: resultText.implicitHeight + 20
              radius: 9
              color: Util.alpha(Color.menu.text, 0.08)
              Text {
                id: resultText
                anchors.fill: parent
                anchors.margins: 10
                text: root.diagnostic.message || ""
                color: Color.menu.text
                font.family: Style.font.menuFamily
                font.pixelSize: Style.font.body
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
              }
            }
            Repeater {
              visible: root.phase === "status"
              model: root.diagnostic.checks || []
              delegate: Rectangle {
                width: diagnosticContent.width
                height: checkText.implicitHeight + 18
                radius: 8
                color: modelData.state === "ok" ? Util.alpha(Color.accent, 0.12) : Util.alpha(Color.menu.text, 0.10)
                Text {
                  id: checkText
                  anchors.fill: parent
                  anchors.margins: 9
                  text: (modelData.state === "ok" ? "✓ " : "! ") + modelData.label + "\n" + modelData.detail
                  color: Color.menu.text
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.body
                  lineHeight: 1.2
                  wrapMode: Text.Wrap
                  textFormat: Text.PlainText
                }
              }
            }
            Text {
              visible: root.phase === "shortcut" && root.diagnostic.binding !== undefined
              width: parent.width
              text: root.words("Definido en ", "Defined in ") + String(root.diagnostic.binding.path || "").split("/").pop() + (root.diagnostic.line ? (", " + root.words("línea", "line") + " " + root.diagnostic.binding.line) : "" + ".")
              color: Util.alpha(Color.menu.text, 0.68)
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.Wrap
            }
            Text {
              visible: root.phase === "shortcut" && root.diagnostic.events !== undefined && root.diagnostic.events.length > 0
              text: root.words("Abrir archivo", "Open file")
              color: Color.accent
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              font.underline: shortcutSourceMouse.containsMouse
              MouseArea { id: shortcutSourceMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.openShortcutSource() }
            }
            Text {
              text: root.words("Volver", "Back")
              color: Color.accent
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              font.underline: backMouse.containsMouse
              MouseArea { id: backMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.open() }
            }
            Text { width: parent.width; text: root.status; color: Util.alpha(Color.menu.text, 0.65); font.family: Style.font.menuFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.Wrap; textFormat: Text.PlainText }
          }
        }
      }
    }
  }
}
