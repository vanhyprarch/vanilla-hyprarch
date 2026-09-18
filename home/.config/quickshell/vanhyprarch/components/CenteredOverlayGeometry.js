.pragma library

function coordinate(origin, extent, surfaceExtent) {
    return origin + Math.floor((extent - surfaceExtent) / 2)
}

function margin(extent, surfaceExtent) {
    return coordinate(0, extent, surfaceExtent)
}

function center(origin, extent, surfaceExtent) {
    return coordinate(origin, extent, surfaceExtent) + surfaceExtent / 2
}
