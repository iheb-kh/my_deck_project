/* =========================
   Simple helpers
   ========================= */

/**
 * Convert a value to epoch seconds.
 * Input: number (ms/s) or date string.
 * Output: integer seconds or NaN.
 */
function toEpochSeconds(value) {
  if (typeof value === 'number') {
    if (value < 1e10) return value;
    return Math.floor(value / 1000);
  }

  const d = new Date(value);
  if (!Number.isFinite(d.getTime())) return NaN;
  return Math.floor(d.getTime() / 1000);
}

/**
 * Format epoch seconds into [date, time].
 * Input: epoch seconds as integer.
 * Output: array [dateString, timeString].
 */
function formatEpoch(epoch) {
  const d = new Date(epoch * 1000);
  const date = d.toLocaleDateString('it-IT');
  const time = d.toLocaleTimeString('it-IT', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
  return [date, time];
}

/**
 * Ensure object is a valid FeatureCollection.
 * Input: any JSON object from API.
 * Output: FeatureCollection with features array.
 */
function normalizeFeatureCollection(fc) {
  if (fc && fc.type === 'FeatureCollection' && Array.isArray(fc.features)) {
    return fc;
  }
  return { type: 'FeatureCollection', features: [] };
}

/**
 * Fetch JSON from URL without cache.
 * Input: url string.
 * Output: parsed JSON object.
 */
async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  return await response.json();
}

/**
 * Compute bounding box for a FeatureCollection.
 * Input: FeatureCollection with geometries.
 * Output: [[minX,minY],[maxX,maxY]] or null.
 */
function getFeatureCollectionBounds(fc) {
  if (!fc || !fc.features) return null;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  let hasData = false;

  function scanCoordinates(coords) {
    if (Array.isArray(coords) && coords.length >= 2 &&
        typeof coords[0] === 'number' && typeof coords[1] === 'number') {
      const x = coords[0];
      const y = coords[1];

      if (Number.isFinite(x) && Number.isFinite(y)) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
        hasData = true;
      }
    } else if (Array.isArray(coords)) {
      for (const item of coords) {
        scanCoordinates(item);
      }
    }
  }

  for (const feature of fc.features) {
    if (feature && feature.geometry && feature.geometry.coordinates) {
      scanCoordinates(feature.geometry.coordinates);
    }
  }

  if (!hasData) {
    return null;
  }

  return [[minX, minY], [maxX, maxY]];
}

/**
 * Get middle point of a LineString coordinates array.
 * Input: coordinates array [[x1,y1],...].
 * Output: [midX, midY] or null.
 */
function getLineMiddlePoint(coords) {
  if (!Array.isArray(coords) || coords.length < 2) return null;

  const first = coords[0];
  const last = coords[coords.length - 1];

  return [
    (first[0] + last[0]) / 2,
    (first[1] + last[1]) / 2
  ];
}

/* =========================
   Peak + per-road values
   ========================= */

/**
 * Choose the road with highest "value" and build marker data.
 * Input: FeatureCollection fc, stats object with min/max.
 * Output: peak object {position,color,size,icon,value} or null.
 */
function getPeakPoint(fc, stats) {
  if (!fc || !fc.features || !fc.features.length) return null;

  let bestFeature = null;
  let bestValue = -Infinity;

  for (const feature of fc.features) {
    if (!feature || !feature.properties) continue;
    const value = Number(feature.properties.value);
    if (!Number.isFinite(value)) continue;

    if (value > bestValue) {
      bestValue = value;
      bestFeature = feature;
    }
  }

  if (!bestFeature || !bestFeature.geometry ||
      bestFeature.geometry.type !== 'LineString') {
    return null;
  }

  const middle = getLineMiddlePoint(bestFeature.geometry.coordinates);
  if (!middle) return null;

  const minValue = stats && Number.isFinite(stats.min) ? stats.min : 0;
  const maxValue = stats && Number.isFinite(stats.max) ? stats.max : 1;

  let ratio = 0;
  if (Number.isFinite(bestValue) && maxValue > minValue) {
    ratio = (bestValue - minValue) / (maxValue - minValue);
  }
  ratio = Math.max(0, Math.min(1, ratio));

  let color = [46, 127, 255, 255];
  if (ratio < 0.33) {
    color = [46, 127, 255, 255];
  } else if (ratio < 0.66) {
    color = [39, 209, 124, 255];
  } else if (ratio < 0.9) {
    color = [255, 212, 77, 255];
  } else {
    color = [255, 59, 59, 255];
  }

  const vehicles = Number(bestFeature.properties.vehicles || 0);
  const size = Math.max(
    22,
    Math.min(56, 14 + Math.sqrt(Math.max(vehicles, 0)) * 6)
  );

  return {
    position: middle,
    color: color,
    size: size,
    icon: 'marker',
    value: bestValue
  };
}

/**
 * Build label data with numeric values for each road.
 * Input: FeatureCollection fc.
 * Output: array of {position, text}.
 */
function buildValuesLabels(fc) {
  const results = [];
  if (!fc || !fc.features) return results;

  for (const feature of fc.features) {
    if (!feature.geometry || feature.geometry.type !== 'LineString') {
      continue;
    }

    const middle = getLineMiddlePoint(feature.geometry.coordinates);
    if (!middle) continue;

    const value = Number(feature.properties && feature.properties.value);
    const labelText = Number.isFinite(value) ? value.toFixed(2) : '';

    results.push({
      position: middle,
      text: labelText
    });
  }

  return results;
}

/* =========================
   Map + layers setup
   ========================= */

/**
 * Create base map instance with default style.
 * Input: none (uses DOM #map).
 * Output: maplibregl.Map instance.
 */
function createBaseMap() {
  return new maplibregl.Map({
    container: 'map',
    style: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
    center: [10.3966, 43.7228],
    zoom: 13,
    pitch: 55,
    bearing: -15
  });
}

/**
 * Create all deck.gl layers used in the map.
 * Input: none (uses global deck).
 * Output: object with all layers.
 */
function createLayers() {
  const { GeoJsonLayer, MapboxLayer, IconLayer, TextLayer } = deck;

  const buildingsLayer = new MapboxLayer({
    id: 'buildings',
    type: GeoJsonLayer,
    data: { type: 'FeatureCollection', features: [] },
    pickable: true,
    stroked: false,
    filled: true,
    extruded: true,
    getElevation: f => Number(f.properties?.HEIGHT ?? 0) || 0,
    getFillColor: [160, 160, 180, 150]
  });

  const roadsLayer = new MapboxLayer({
    id: 'roads',
    type: GeoJsonLayer,
    data: { type: 'FeatureCollection', features: [] },
    pickable: false,
    filled: false,
    stroked: true,
    getLineColor: [60, 90, 140, 220],
    getLineWidth: 3,
    lineWidthUnits: 'pixels'
  });

  let currentStats = { min: 0, max: 1 };

  const trafficLayer = new MapboxLayer({
    id: 'traffic',
    type: GeoJsonLayer,
    data: { type: 'FeatureCollection', features: [] },
    pickable: false,
    filled: false,
    stroked: true,
    lineWidthUnits: 'pixels',
    lineWidthMinPixels: 2,
    lineWidthMaxPixels: 7,
    getLineWidth: feature => {
      const vehicles = Number(feature.properties?.vehicles || 0);
      return Math.max(3, Math.min(9, Math.sqrt(vehicles) / 1.6));
    },
    getLineColor: feature => {
      const value = Number(feature.properties?.value ?? 0);
      const minValue = currentStats.min;
      const maxValue = currentStats.max;

      let ratio = 0;
      if (Number.isFinite(value) && maxValue > minValue) {
        ratio = (value - minValue) / (maxValue - minValue);
      }
      ratio = Math.max(0, Math.min(1, ratio));

      if (ratio < 0.33) return [46, 127, 255, 210];
      if (ratio < 0.66) return [39, 209, 124, 210];
      if (ratio < 0.9) return [255, 212, 77, 210];
      return [255, 59, 59, 220];
    },
    updateTriggers: {
      getLineColor: [() => currentStats.min, () => currentStats.max]
    }
  });

  const peakIconLayer = new MapboxLayer({
    id: 'frame-peak',
    type: IconLayer,
    data: [],
    iconAtlas: 'https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png',
    iconMapping: {},
    getIcon: () => 'marker',
    getPosition: d => d.position,
    getSize: d => d.size,
    sizeUnits: 'pixels',
    sizeScale: 1,
    getColor: d => d.color,
    billboard: true,
    pickable: false
  });

  const valuesTextLayer = new MapboxLayer({
    id: 'values-text',
    type: TextLayer,
    data: [],
    getPosition: d => d.position,
    getText: d => d.text,
    getSize: 12,
    getColor: [30, 30, 30, 230],
    getTextAnchor: 'middle',
    background: true,
    getBackgroundColor: [255, 255, 255, 220],
    backgroundPadding: [4, 2],
    getPixelOffset: [0, -10]
  });

  return {
    buildingsLayer,
    roadsLayer,
    trafficLayer,
    peakIconLayer,
    valuesTextLayer,
    get currentStats() {
      return currentStats;
    },
    set currentStats(value) {
      currentStats = value;
    }
  };
}

/* =========================
   Timeline + UI state
   ========================= */

let timeMin = null;
let timeMax = null;
let playInterval = null;

const slider = document.getElementById('time-slider');
const btnPrev = document.getElementById('btn-prev');
const btnPlay = document.getElementById('btn-play');
const btnNext = document.getElementById('btn-next');

const classSelect = document.getElementById('class-select');
const metricSelect = document.getElementById('metric-select');
const legendMinLabel = document.getElementById('legend-min');
const legendMaxLabel = document.getElementById('legend-max');
const timeStartLabel = document.getElementById('time-start');

const chkTraffic = document.getElementById('chk-traffic');
const chkBuildings = document.getElementById('chk-buildings');
const chkRoads = document.getElementById('chk-roads');
const chkRumore = document.getElementById('chk-rumore');
const chkValues = document.getElementById('chk-values');

const legendCard = document.getElementById('legend-card');
const timelineCard = document.getElementById('timeline-card');
const noDataMessage = document.getElementById('no-data-message');

const btnZoomIn = document.getElementById('btn-zoom-in');
const btnZoomOut = document.getElementById('btn-zoom-out');
const btnSatellite = document.getElementById('btn-satellite');
const btn3D = document.getElementById('btn-3d');

const tooltip = document.getElementById('map-tooltip');

/**
 * Enable or disable timeline controls.
 * Input: isEnabled boolean.
 * Output: none (updates DOM and timers).
 */
function setTimelineEnabled(isEnabled) {
  slider.disabled = !isEnabled;
  btnPrev.disabled = !isEnabled;
  btnPlay.disabled = !isEnabled;
  btnNext.disabled = !isEnabled;

  if (!isEnabled && playInterval) {
    clearInterval(playInterval);
    playInterval = null;

    const playIcon = document.getElementById('play-icon');
    playIcon.classList.remove('fa-pause');
    playIcon.classList.add('fa-play');
  }
}

/**
 * Update timeline and legend visibility based on checkboxes.
 * Input: none (reads chkTraffic/chkRumore).
 * Output: none (updates DOM classes).
 */
function updateTimelineAndLegendVisibility() {
  const showTraffic = chkTraffic.checked;
  const showRumore = chkRumore.checked;

  if (showTraffic || showRumore) {
    timelineCard.classList.remove('hidden');

    if (showTraffic) {
      setTimelineEnabled(true);
      noDataMessage.classList.add('hidden');
      timelineCard.classList.remove('disabled-overlay');
    } else {
      setTimelineEnabled(false);
      noDataMessage.classList.remove('hidden');
      timelineCard.classList.add('disabled-overlay');
    }
  } else {
    timelineCard.classList.add('hidden');
    legendCard.classList.add('hidden');
    return;
  }

  if (showTraffic) {
    legendCard.classList.remove('hidden');
  } else {
    legendCard.classList.add('hidden');
  }
}

/**
 * Convert slider position to epoch seconds.
 * Input: none (reads slider/timeMin/timeMax).
 * Output: epoch seconds or null.
 */
function getSliderEpoch() {
  if (!Number.isFinite(timeMin) || !Number.isFinite(timeMax)) {
    return null;
  }
  const position = Number(slider.value) / Number(slider.max);
  const epoch = timeMin + position * (timeMax - timeMin);
  return Math.round(epoch);
}

/**
 * Build a time window around a center.
 * Input: centerEpoch (seconds), minutesRange (int).
 * Output: [fromEpoch, toEpoch].
 */
function getWindowFromEpoch(centerEpoch, minutesRange) {
  const seconds = minutesRange * 60;
  return [centerEpoch - seconds, centerEpoch + seconds];
}

/**
 * Paint the played portion of the slider.
 * Input: none (reads slider value/max).
 * Output: none (updates CSS variable).
 */
function paintSliderFill() {
  const percent =
    (Number(slider.value) / Number(slider.max)) * 100;
  slider.style.setProperty('--played', percent + '%');
}

/**
 * Update the small time label above the player.
 * Input: none (reads slider).
 * Output: none (updates DOM).
 */
function updateLiveTimeLabel() {
  const epoch = getSliderEpoch();
  if (epoch == null) return;
  const [, timeText] = formatEpoch(epoch);
  timeStartLabel.textContent = timeText;
}

/**
 * Load traffic frame for current slider position.
 * Input: layers object (traffic, peakIcon, valuesText, stats link).
 * Output: none (updates layers + legend).
 */
async function loadTrafficForCurrentSlider(layers) {
  if (!chkTraffic.checked) {
    return;
  }

  const epoch = getSliderEpoch();
  if (epoch == null) return;

  const [fromEpoch, toEpoch] = getWindowFromEpoch(epoch, 5);
  const vehicleClass = classSelect.value;
  const metric = metricSelect.value;

  const url =
    `/api/map/traffic?fr=${fromEpoch}` +
    `&to=${toEpoch}` +
    `&veh_class=${encodeURIComponent(vehicleClass)}` +
    `&metric=${encodeURIComponent(metric)}`;

  const response = await fetchJson(url);
  const featureCollection = normalizeFeatureCollection(response);

  layers.currentStats = response.stats || { min: 0, max: 1 };

  if (Number.isFinite(layers.currentStats.min)) {
    legendMinLabel.textContent = layers.currentStats.min.toFixed(2);
  } else {
    legendMinLabel.textContent = 'min';
  }

  if (Number.isFinite(layers.currentStats.max)) {
    legendMaxLabel.textContent = layers.currentStats.max.toFixed(2);
  } else {
    legendMaxLabel.textContent = 'max';
  }

  layers.trafficLayer.setProps({ data: featureCollection });

  const peak = getPeakPoint(featureCollection, layers.currentStats);
  layers.peakIconLayer.setProps({ data: peak ? [peak] : [] });

  if (chkValues.checked) {
    const labels = buildValuesLabels(featureCollection);
    layers.valuesTextLayer.setProps({ data: labels });
  } else {
    layers.valuesTextLayer.setProps({ data: [] });
  }
}

/* =========================
   Tooltip helpers
   ========================= */

/**
 * Show tooltip near mouse position.
 * Input: x,y in pixels and html string.
 * Output: none (updates tooltip DOM).
 */
function showTooltip(x, y, html) {
  tooltip.style.display = 'block';
  tooltip.style.left = (x + 12) + 'px';
  tooltip.style.top = (y + 12) + 'px';
  tooltip.innerHTML = html;
}

/**
 * Hide tooltip.
 * Input: none.
 * Output: none.
 */
function hideTooltip() {
  tooltip.style.display = 'none';
}

/* =========================
   Main init
   ========================= */

document.addEventListener('DOMContentLoaded', async () => {
  const map = createBaseMap();
  const layers = createLayers();

  // Top controls events
  btnZoomIn.addEventListener('click', () => map.zoomIn());
  btnZoomOut.addEventListener('click', () => map.zoomOut());

  btnSatellite.addEventListener('click', () => {
    btnSatellite.classList.toggle('active');
    if (btnSatellite.classList.contains('active')) {
      map.setStyle(
        'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
      );
    } else {
      map.setStyle(
        'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json'
      );
    }
  });

  btn3D.addEventListener('click', () => {
    btn3D.classList.toggle('active');
    if (btn3D.classList.contains('active')) {
      map.easeTo({ pitch: 60, bearing: -15 });
    } else {
      map.easeTo({ pitch: 0, bearing: 0 });
    }
  });

  // Checkbox: buildings
  chkBuildings.addEventListener('change', () => {
    layers.buildingsLayer.setProps({ visible: chkBuildings.checked });
  });

  // Checkbox: roads
  chkRoads.addEventListener('change', () => {
    layers.roadsLayer.setProps({ visible: chkRoads.checked });
  });

  // Checkbox: traffic
  chkTraffic.addEventListener('change', () => {
    const visible = chkTraffic.checked;

    layers.trafficLayer.setProps({ visible: visible });
    layers.peakIconLayer.setProps({ visible: visible });
    layers.valuesTextLayer.setProps({ visible: visible });

    updateTimelineAndLegendVisibility();

    if (visible) {
      loadTrafficForCurrentSlider(layers);
    }
  });

  // Checkbox: rumore (not implemented, UI only)
  chkRumore.addEventListener('change', () => {
    console.log('Rumore checkbox toggled - no behavior implemented yet');
    updateTimelineAndLegendVisibility();
  });

  // Checkbox: show values
  chkValues.addEventListener('change', () => {
    loadTrafficForCurrentSlider(layers);
  });

  // Slider change
  slider.addEventListener('input', () => {
    if (!chkTraffic.checked) return;
    paintSliderFill();
    updateLiveTimeLabel();
    loadTrafficForCurrentSlider(layers);
  });

  // Class and metric select
  classSelect.addEventListener('change', () => {
    loadTrafficForCurrentSlider(layers);
  });

  metricSelect.addEventListener('change', () => {
    loadTrafficForCurrentSlider(layers);
  });

  // Prev / next buttons
  btnPrev.addEventListener('click', () => {
    if (!chkTraffic.checked) return;
    const current = Number(slider.value);
    slider.value = Math.max(0, current - 20);
    paintSliderFill();
    updateLiveTimeLabel();
    loadTrafficForCurrentSlider(layers);
  });

  btnNext.addEventListener('click', () => {
    if (!chkTraffic.checked) return;
    const current = Number(slider.value);
    const max = Number(slider.max);
    slider.value = Math.min(max, current + 20);
    paintSliderFill();
    updateLiveTimeLabel();
    loadTrafficForCurrentSlider(layers);
  });

  // Play / pause
  btnPlay.addEventListener('click', () => {
    if (!chkTraffic.checked) return;
console.log('Rendered roads layer data length:', layers);

    const icon = document.getElementById('play-icon');
    const isPlaying = icon.classList.contains('fa-pause');

    if (isPlaying) {
      clearInterval(playInterval);
      playInterval = null;
      icon.classList.remove('fa-pause');
      icon.classList.add('fa-play');
      return;
    }

    icon.classList.remove('fa-play');
    icon.classList.add('fa-pause');

    playInterval = setInterval(() => {
      const current = Number(slider.value);
      const max = Number(slider.max);

      if (current >= max) {
        slider.value = 0;
      } else {
        slider.value = current + 2;
      }

      paintSliderFill();
      updateLiveTimeLabel();
      loadTrafficForCurrentSlider(layers);
    }, 350);
  });

  // When map loads: add layers and fetch data
  map.on('load', async () => {
    map.addLayer(layers.roadsLayer);
    map.addLayer(layers.buildingsLayer);
    map.addLayer(layers.trafficLayer);
    map.addLayer(layers.peakIconLayer);
    map.addLayer(layers.valuesTextLayer);

    try {
      const iconMapping = await fetchJson(
        'https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.json'
      );
      layers.peakIconLayer.setProps({ iconMapping: iconMapping });
    } catch (error) {
      console.error('Error loading icon mapping', error);
    }

    const roadsFC = normalizeFeatureCollection(
      await fetchJson('/api/map/roads_static')
    );
    layers.roadsLayer.setProps({ data: roadsFC });

    const buildingsFC = normalizeFeatureCollection(
      await fetchJson('/api/map/buildings?limit=100000')
    );
    layers.buildingsLayer.setProps({ data: buildingsFC });
console.log('Rendered roads layer data length:', layers);

    const bounds = getFeatureCollectionBounds(roadsFC);
    if (bounds) {
      try {
        map.fitBounds(bounds, {
          padding: 60,
          maxZoom: 15,
          duration: 900
        });
        setTimeout(() => {
          const newZoom = Math.min(16.5, map.getZoom() + 1);
          map.easeTo({ zoom: newZoom, duration: 700 });
        }, 950);
      } catch (error) {
        console.error('Error fitting bounds', error);
      }
    }

    const meta = await fetchJson('/api/map/meta');
    const rawMin =
      meta?.traffic?.time_min ?? meta?.traffic_time_range?.min;
    const rawMax =
      meta?.traffic?.time_max ?? meta?.traffic_time_range?.max;

    timeMin = toEpochSeconds(rawMin);
    timeMax = toEpochSeconds(rawMax);

    const [startDate, startTime] = formatEpoch(timeMin);
    const [endDate, endTime] = formatEpoch(timeMax);

    timeStartLabel.textContent = startTime;
    document.getElementById('date-left').textContent =
      `${startDate} — ${startTime}`;
    document.getElementById('date-right').textContent =
      `${endDate} — ${endTime}`;

    slider.disabled = false;
    btnPrev.disabled = false;
    btnPlay.disabled = false;
    btnNext.disabled = false;

    paintSliderFill();
    updateTimelineAndLegendVisibility();
    await loadTrafficForCurrentSlider(layers);
  });

  // Building tooltip
  layers.buildingsLayer.setProps({
    onHover: info => {
      if (info && info.object && Number.isFinite(info.x) && Number.isFinite(info.y)) {
        const props = info.object.properties || {};
        const height = props.HEIGHT ?? '—';
        const pop = props.POP ?? '—';
        const html =
          `<b>Edificio</b><br/>Altezza: ${height}<br/>Popolazione: ${pop}`;
        showTooltip(info.x, info.y, html);
      } else {
        hideTooltip();
      }
    }
  });

  map.on('mouseout', hideTooltip);
});
