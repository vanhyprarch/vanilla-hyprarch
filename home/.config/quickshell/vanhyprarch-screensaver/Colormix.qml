import QtQuick

/*
 * Visual algorithm derived from Ly's src/animations/ColorMix.zig at commit
 * 863162b5f79850c08fda13a3fbde7e19aac544ba. Ly is distributed under the
 * Do What The Fuck You Want To Public License, Version 2 (WTFPL).
 */
Item {
    id: root

    required property real animationFrames

    /* Match the logical cell pitch of the Foot+C visual reference. */
    readonly property real cellWidth: 9.6
    readonly property real cellHeight: 22.6
    readonly property real patternCosMod: Math.random() * Math.PI * 2.0
    readonly property real patternSinMod: Math.random() * Math.PI * 2.0

    /*
     * Ly's foreground/background pairs and block-density order, represented
     * as their blended cell colors: red/blue, blue/true-black, true-black/red.
     */
    readonly property var cellColors: [
        "#ff0000", "#bf0040", "#800080", "#4000bf",
        "#0000ff", "#0000bf", "#000080", "#000040",
        "#000000", "#400000", "#800000", "#bf0000"
    ]

    Canvas {
        id: canvas

        width: Math.max(1, Math.ceil(root.width / root.cellWidth))
        height: Math.max(1, Math.ceil(root.height / root.cellHeight))
        transformOrigin: Item.TopLeft
        transform: Scale {
            xScale: root.width / canvas.width
            yScale: root.height / canvas.height
        }
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Threaded
        smooth: false
        canvasSize: Qt.size(width, height)

        onCanvasSizeChanged: requestPaint()

        onPaint: {
            const context = getContext("2d")
            const columns = Math.max(1, Math.round(canvasSize.width))
            const rows = Math.max(1, Math.round(canvasSize.height))

            const time = root.animationFrames * 0.01
            const patternCosMod = root.patternCosMod
            const patternSinMod = root.patternSinMod
            const palette = root.cellColors

            for (let y = 0; y < rows; ++y) {
                let runStart = 0
                let runPaletteIndex = -1

                for (let x = 0; x < columns; ++x) {
                    let uvX = (x * 2.0 - columns) / (rows * 2.0)
                    let uvY = (y * 2.0 - rows) / rows
                    let uv2X = uvX + uvY
                    let uv2Y = uvX + uvY

                    for (let iteration = 0; iteration < 3; ++iteration) {
                        const length = Math.sqrt(uvX * uvX + uvY * uvY)
                        uv2X += uvX + length
                        uv2Y += uvY + length
                        uvX += 0.5 * Math.cos(
                            patternCosMod + uv2Y * 0.2 + time * 0.1)
                        uvY += 0.5 * Math.sin(
                            patternSinMod + uv2X - time * 0.1)
                        const shared = Math.cos(uvX + uvY)
                            - Math.sin(uvX * 0.7 - uvY)
                        uvX -= shared
                        uvY -= shared
                    }

                    const paletteIndex = Math.floor(
                        Math.sqrt(uvX * uvX + uvY * uvY) * 5.0) % 12
                    if (paletteIndex !== runPaletteIndex) {
                        if (runPaletteIndex >= 0) {
                            context.fillStyle = palette[runPaletteIndex]
                            context.fillRect(runStart, y, x - runStart, 1)
                        }
                        runStart = x
                        runPaletteIndex = paletteIndex
                    }
                }

                context.fillStyle = palette[runPaletteIndex]
                context.fillRect(runStart, y, columns - runStart, 1)
            }
        }

        Connections {
            target: root

            function onAnimationFramesChanged(): void {
                canvas.requestPaint()
            }
        }
    }
}
