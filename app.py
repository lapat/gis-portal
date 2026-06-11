# ==============================================================================
# JENNINGS GIS MASTER PORTAL — ALL COUNTIES — VERSION v1.0.0
# ==============================================================================

import json
import re
import html as html_lib
import os
import requests
import streamlit as st
import folium

st.set_page_config(
    page_title="Jennings GIS Master Portal",
    page_icon="📍",
    layout="centered"
)

st.markdown("""
    <style>
    .block-container { padding-top: 2rem !important; padding-bottom: 2rem !important; }
    h1 { color: #1e293b !important; font-weight: 800 !important; }
    h3 { color: #475569 !important; font-weight: 600 !important; }
    div.stButton > button:first-child {
        background-color: #16a34a !important;
        border-color: #16a34a !important;
        color: white !important;
        font-weight: 700 !important;
        padding: 0.5rem 2rem !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #15803d !important;
        border-color: #15803d !important;
    }
    </style>
""", unsafe_allow_html=True)


# ── PIN normalization helpers ──────────────────────────────────────────────────

def _digits(p):
    return re.sub(r'[^0-9]', '', p)

def _normalize(p):
    """Strip all non-alphanumeric for universal comparison."""
    return re.sub(r'[^0-9a-zA-Z]', '', str(p)).strip()

def _strip(p):
    return p.replace("-", "").replace(" ", "").strip()

def _fmt_2_2_3_3(p):
    """##-##-###-### from 10 raw digits."""
    d = _digits(p)
    if len(d) == 10:
        return f"{d[0:2]}-{d[2:4]}-{d[4:7]}-{d[7:10]}"
    return p.strip()

def _fmt_kankakee(p):
    """##-##-##-###-### (12 raw digits)."""
    d = _digits(p)
    if len(d) == 12:
        return f"{d[0:2]}-{d[2:4]}-{d[4:6]}-{d[6:9]}-{d[9:12]}"
    return p.strip()


# ── County configuration ───────────────────────────────────────────────────────
# Keys: url, query_field, display_field, extra_out_fields,
#       clean (fn: raw str → query str), query_style ("like"|"exact"),
#       sample (placeholder text), hint (help string), timeout

COUNTY_CONFIGS = {
    "Cook County": {
        "url": "https://gis.cookcountyil.gov/traditional/rest/services/cookVwrDynmc/MapServer/44/query",
        "query_field": "PIN14",
        "display_field": "PIN14",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "like",
        "sample": "01011000020000",
        "hint": "14 digits, no dashes. Dashes are ignored.",
        "timeout": 30,
    },
    "DeKalb County": {
        "url": "https://services7.arcgis.com/hEXJrPwm89CLXBYe/arcgis/rest/services/DeKalbIL_Parcels/FeatureServer/0/query",
        "query_field": "Parcel_Number",
        "display_field": "Parcel_Number",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "like",
        "sample": "0101100001",
        "hint": "10 digits, no dashes. Dashes are ignored.",
        "timeout": 15,
    },
    "DuPage County": {
        "url": "https://gis.dupageco.org/arcgis/rest/services/ParcelSearch/DuPageAssessmentParcelSearch/MapServer/3/query",
        "query_field": "PIN",
        "display_field": "PIN",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "like",
        "sample": "0904403011",
        "hint": "10 digits, no dashes. Dashes are ignored.",
        "timeout": 15,
    },
    "Grundy County": {
        "url": "https://maps.grundyco.org/arcgis/rest/services/CountyWebsiteMaps/CountyParcelsBaseLayer_SPIE/MapServer/0/query",
        "query_field": "Grundy_Master.SDEDATA.Parcel_Poly.PIN",
        "display_field": "Grundy_Master.SDEDATA.Parcel_Poly.PIN",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "exact",
        "sample": "1204377010",
        "hint": "10 digits, no dashes. Dashes are ignored.",
        "timeout": 15,
    },
    "Iroquois County": {
        "url": "https://services6.arcgis.com/6FZQl5a5SiSFMv8P/arcgis/rest/services/Parcels/FeatureServer/0/query",
        "query_field": "ParcelNumber",
        "display_field": "ParcelNumber",
        "extra_out_fields": [],
        "clean": _fmt_2_2_3_3,
        "query_style": "exact",
        "sample": "26-36-100-005",
        "hint": "Format: ##-##-###-### (dashes optional — auto-formatted).",
        "timeout": 15,
    },
    "Kane County": {
        "url": "https://gistech.countyofkane.org/arcgis/rest/services/KanePINList/MapServer/0/query",
        "query_field": "PIN",
        "display_field": "PIN",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "like",
        "sample": "0101100001",
        "hint": "10 digits, no dashes. Dashes are ignored.",
        "timeout": 15,
    },
    "Kankakee County": {
        "url": "https://k3gis.net/arcgis/rest/services/Cadastral/Tax_Parcels_and_Subdivisions/MapServer/0/query",
        "query_field": "pin",
        "display_field": "pin",
        "extra_out_fields": [],
        "clean": _fmt_kankakee,
        "query_style": "exact",
        "sample": "10-27-04-102-023",
        "hint": "Format: ##-##-##-###-### (dashes optional — auto-formatted).",
        "timeout": 15,
    },
    "Kendall County": {
        "url": "https://maps.co.kendall.il.us/server/rest/services/Hosted/fabric_hosted/FeatureServer/1/query",
        "query_field": "pin_dashless",
        "display_field": "pin",
        "extra_out_fields": ["pin"],
        "clean": _strip,
        "query_style": "like",
        "sample": "01-06-100-006",
        "hint": "10 digits or ##-##-###-### with dashes. Dashes are ignored.",
        "timeout": 15,
    },
    "Lake County": {
        "url": "https://maps.lakecountyil.gov/arcgis/rest/services/GISMapping/WABParcels/MapServer/12/query",
        "query_field": "PIN",
        "display_field": "PIN",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "like",
        "sample": "01-01-406-010",
        "hint": "10 digits or ##-##-###-### with dashes. Dashes are ignored.",
        "timeout": 15,
    },
    "LaSalle County": {
        "url": "https://gis.lasallecounty.org/arcgis/rest/services/TaxParcels/MapServer/0/query",
        "query_field": "PIN",
        "display_field": "PIN",
        "extra_out_fields": [],
        "clean": _fmt_2_2_3_3,
        "query_style": "exact",
        "sample": "33-25-123-011",
        "hint": "Format: ##-##-###-### (dashes optional — auto-formatted).",
        "timeout": 15,
    },
    "McHenry County": {
        "url": "https://services1.arcgis.com/6iYC5AXXYapRVNzl/arcgis/rest/services/McHenry_County_TaxParcels/FeatureServer/0/query",
        "query_field": "ParcelNumber",
        "display_field": "ParcelNumber",
        "extra_out_fields": [],
        "clean": _fmt_2_2_3_3,
        "query_style": "exact",
        "sample": "14-21-301-003",
        "hint": "Format: ##-##-###-### (dashes optional — auto-formatted).",
        "timeout": 15,
    },
    "Will County": {
        "url": "https://gis.willcountyillinois.com/server/rest/services/HistoricParcels/Historic_Parcels/MapServer/0/query",
        "query_field": "PIN",
        "display_field": "PIN",
        "extra_out_fields": [],
        "clean": _strip,
        "query_style": "like",
        "sample": "07-01-02-105-021-0000",
        "hint": "Dashes are ignored.",
        "timeout": 15,
    },
}


# ── UI ─────────────────────────────────────────────────────────────────────────

st.title("📍 Jennings Property Search Portal")
st.subheader("Multi-County 11x17 Portfolio Generator")

selected_county = st.selectbox(
    "Select County:",
    options=list(COUNTY_CONFIGS.keys()),
    index=list(COUNTY_CONFIGS.keys()).index("Will County"),
)

cfg = COUNTY_CONFIGS[selected_county]

st.write(
    f"Paste your list of **{selected_county}** PIN numbers straight out of Excel. "
    "The system will compile every single map into **one combined print portfolio**. "
    "When you click print once, the browser automatically splits each property onto its own 11x17 sheet."
)

raw_pin_input = st.text_area(
    label=f"Enter {selected_county} Property Index Numbers (PINs):",
    value=cfg["sample"],
    height=240,
    help=cfg["hint"],
)

county_slug = selected_county.lower().replace(" ", "_").replace("/", "_")
OUTPUT_HTML_NAME = f"jennings_{county_slug}_master_print_portfolio.html"

if st.button("🚀 Compile Unified 11x17 Print Layout"):

    normalized_input = raw_pin_input.replace('\n', ',').replace('\r', ',').replace('\t', ',').replace(';', ',')
    target_pins = [p.strip() for p in normalized_input.split(',') if p.strip()]

    if not target_pins:
        st.error("❌ Please provide at least one valid PIN number.")
    else:
        if os.path.exists(OUTPUT_HTML_NAME):
            os.remove(OUTPUT_HTML_NAME)

        successful_compilation_count = 0
        failed_pins = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        master_frames_html = ""

        q_field = cfg["query_field"]
        d_field = cfg["display_field"]
        out_fields = ",".join([q_field] + [f for f in cfg["extra_out_fields"] if f != q_field])
        timeout = cfg["timeout"]

        for idx, current_pin in enumerate(target_pins):
            progress_bar.progress(int((idx / len(target_pins)) * 100))
            status_text.markdown(
                f"**Mapping [{idx+1}/{len(target_pins)}]:** "
                f"Indexing {selected_county} layers for PIN `{current_pin}`..."
            )

            clean_pin = cfg["clean"](current_pin)
            if not clean_pin:
                continue

            try:
                # ── Step 1: PIN lookup ───────────────────────────────────────
                if cfg["query_style"] == "like":
                    where_clause = f"{q_field} LIKE '%{clean_pin}%'"
                else:
                    where_clause = f"{q_field} = '{clean_pin}'"

                res = requests.get(
                    cfg["url"],
                    params={
                        "where": where_clause,
                        "outFields": out_fields,
                        "f": "geojson",
                        "returnGeometry": "true",
                        "outSR": "4326",
                    },
                    timeout=timeout,
                )
                res.raise_for_status()
                target_payload = res.json()

                target_features = target_payload.get("features", [])
                if not target_features:
                    failed_pins.append((current_pin, f"PIN not found in {selected_county} GIS"))
                    continue

                primary_parcel = target_features[0]
                geometry = primary_parcel.get("geometry", {})
                props = primary_parcel.get("properties", {})

                server_q_pin = str(props.get(q_field, current_pin)).strip()
                server_d_pin = str(props.get(d_field, server_q_pin)).strip()

                # ── Step 2: Centroid ─────────────────────────────────────────
                if geometry["type"] == "Polygon":
                    coordinates_array = geometry["coordinates"][0]
                else:
                    coordinates_array = geometry["coordinates"][0][0]

                lats = [coord[1] for coord in coordinates_array]
                lons = [coord[0] for coord in coordinates_array]
                centroid_lat = (max(lats) + min(lats)) / 2
                centroid_lon = (max(lons) + min(lons)) / 2

                # ── Step 3: Neighbor query ───────────────────────────────────
                spatial_envelope_geom = {
                    "xmin": centroid_lon - 0.007,
                    "ymin": centroid_lat - 0.005,
                    "xmax": centroid_lon + 0.007,
                    "ymax": centroid_lat + 0.005,
                    "spatialReference": {"wkid": 4326},
                }

                matrix_res = requests.get(
                    cfg["url"],
                    params={
                        "geometry": json.dumps(spatial_envelope_geom),
                        "geometryType": "esriGeometryEnvelope",
                        "spatialRel": "esriSpatialRelIntersects",
                        "outFields": out_fields,
                        "f": "geojson",
                        "returnGeometry": "true",
                        "outSR": "4326",
                        "maxAllowableOffset": "0.00001",
                    },
                    timeout=timeout,
                )
                matrix_res.raise_for_status()
                matrix_payload = matrix_res.json()

                # ── Step 4: Build map ────────────────────────────────────────
                map_instance = folium.Map(
                    location=[centroid_lat, centroid_lon],
                    zoom_start=16,
                    tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
                    attr="&copy; OpenStreetMap contributors &copy; CARTO",
                )

                match_key = _normalize(server_q_pin)

                def style_router(feature, _mk=match_key, _qf=q_field):
                    feat_pin = _normalize(str(feature.get("properties", {}).get(_qf, "")))
                    if feat_pin and feat_pin == _mk:
                        return {"fillColor": "#16a34a", "color": "#15803d", "weight": 3.5, "fillOpacity": 0.25}
                    return {"fillColor": "none", "color": "#d97706", "weight": 1.2, "fillOpacity": 0.0}

                tooltip_field = d_field
                folium.GeoJson(
                    matrix_payload,
                    style_function=style_router,
                    tooltip=folium.GeoJsonTooltip(
                        fields=[tooltip_field],
                        aliases=["PIN:"],
                        localize=True,
                    ),
                ).add_to(map_instance)

                map_instance.get_root().header.add_child(folium.Element(f"""
                <div class="pin-display-banner">{selected_county.upper()} PROPERTY PIN: {server_d_pin}</div>
                <style>
                html, body {{ margin: 0 !important; padding: 0 !important; width: 11in !important; height: 17in !important; background: #ffffff !important; }}
                .pin-display-banner {{
                    position: absolute; top: 25px; left: 25px; z-index: 99999; background: rgba(255,255,255,0.95);
                    color: #1e293b; padding: 10px 18px; border-radius: 6px; font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 16px; font-weight: 700; letter-spacing: 0.5px; border: 2px solid #15803d; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                }}
                .folium-map, #map, .leaflet-container {{ position: absolute !important; top: 0 !important; left: 0 !important; width: 11in !important; height: 17in !important; margin: 0 !important; padding: 0 !important; }}
                .leaflet-control-zoom, .leaflet-control-attribution {{ display: none !important; }}
                @media print {{
                    .pin-display-banner {{ background: #ffffff !important; border: 2px solid #15803d !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                    @page {{ size: 11in 17in portrait; margin: 0in !important; }}
                }}
                </style>
                """))

                html_raw_string = map_instance.get_root().render()
                srcdoc_escaped = html_lib.escape(html_raw_string, quote=True)

                master_frames_html += f"""
                <div class="page-container">
                    <iframe class="isolated-map-frame" srcdoc="{srcdoc_escaped}"></iframe>
                </div>
                """
                successful_compilation_count += 1

            except requests.exceptions.RequestException as e:
                failed_pins.append((current_pin, f"Network error: {e}"))
            except (KeyError, IndexError, ValueError) as e:
                failed_pins.append((current_pin, f"Geometry parse error: {e}"))
            except Exception as e:
                failed_pins.append((current_pin, str(e)))

        progress_bar.progress(100)
        status_text.empty()

        if successful_compilation_count > 0:
            master_document_payload = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Jennings GIS Master Print Portfolio — {selected_county}</title>
    <style>
        html, body {{ margin: 0 !important; padding: 0 !important; background: #ffffff !important; }}
        .page-container {{
            position: relative; width: 11in !important; height: 17in !important;
            page-break-after: always; page-break-inside: avoid; overflow: hidden; background: #ffffff !important;
        }}
        .page-container:last-child {{ page-break-after: avoid !important; }}
        .isolated-map-frame {{
            border: none !important; margin: 0 !important; padding: 0 !important;
            width: 11in !important; height: 17in !important; overflow: hidden;
        }}
        @media screen {{
            body {{ background-color: #f1f5f9 !important; display: flex; flex-direction: column; align-items: center; gap: 40px; padding: 40px 0; }}
            .page-container {{ box-shadow: 0 10px 25px rgba(0,0,0,0.15); border: 1px solid #cbd5e1; }}
            .print-trigger-btn {{
                display: block !important; position: fixed; top: 25px; right: 25px; z-index: 999999;
                background: #15803d; color: white; padding: 12px 24px; border: none; border-radius: 6px;
                font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; font-weight: bold;
                cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
        }}
        @media print {{
            body {{ background: #ffffff !important; }}
            .page-container {{ border: none !important; margin: 0 !important; }}
            @page {{ size: 11in 17in portrait; margin: 0in !important; }}
        }}
    </style>
</head>
<body>
    <button class="print-trigger-btn" onclick="window.print();">🖨️ Print Entire Portfolio ({successful_compilation_count} Pages)</button>
    {master_frames_html}
</body>
</html>
"""
            with open(OUTPUT_HTML_NAME, "w", encoding="utf-8") as f:
                f.write(master_document_payload)

            st.success(f"🎉 Success! Compiled {successful_compilation_count} property map sheet(s) for {selected_county}.")

            if failed_pins:
                with st.expander(f"⚠️ {len(failed_pins)} PIN(s) could not be mapped"):
                    for pin, reason in failed_pins:
                        st.write(f"- `{pin}`: {reason}")

            with open(OUTPUT_HTML_NAME, "rb") as f:
                st.download_button(
                    label="📥 Download Master 11x17 Portfolio Document",
                    data=f.read(),
                    file_name=OUTPUT_HTML_NAME,
                    mime="text/html",
                    use_container_width=True,
                )
        else:
            st.error(f"❌ No maps could be generated. Verify PINs or check {selected_county} GIS server availability.")
            if failed_pins:
                with st.expander("Error details"):
                    for pin, reason in failed_pins:
                        st.write(f"- `{pin}`: {reason}")
