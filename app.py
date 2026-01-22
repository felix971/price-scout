"""
Price Scout Streamlit Application.

This module provides a web-based user interface for comparing computer parts prices
across multiple Australian vendors. It features single MPN queries, batch CSV processing,
and analytics with price trend visualization.

Features:
    - Single MPN price comparison across 5 vendors
    - CSV batch processing for multiple products
    - Price history tracking and analytics
    - Interactive charts and visualizations
    - Database integration for historical data

Vendors Supported:
    - Scorptec Computers
    - Mwave Australia
    - PC Case Gear
    - JW Computers
    - Umart
    - Digicor
    - Centrecom
    - Computer Alliance
    - CPL
"""

import time
import asyncio
import pandas as pd
from io import StringIO
from datetime import datetime
from scraper import scrape_mpn_single
from db.db_manager import DatabaseManager
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px


# Vendor display names mapping
vendor_names = {
    "digicor": "Digicor",
    "scorptec": "Scorptec Computers",
    "mwave": "Mwave Australia",
    "pc_case_gear": "PC Case Gear",
    "jw_computers": "JW Computers",
    "umart": "Umart",
    "centrecom": "Centrecom",
    "computeralliance": "Computer Alliance",
    "cpl": "CPL"
}


@st.cache_resource
def get_db_connection():
    """
    Initialize and cache the DatabaseManager instance.

    Uses Streamlit's cache_resource decorator to ensure only one database
    connection is created and reused across the application lifecycle.

    Returns:
        DatabaseManager: Cached database manager instance for the application.
    """
    return DatabaseManager()


# Initialize cached database connection
db = get_db_connection()


def process_and_save_result(mpn: str, vendor_name: str, found: bool, price: float):
    """
    Process and save a vendor's price result to the database.

    Implements smart price tracking:
    - If price changed: adds new record
    - If price same: updates timestamp of existing record

    Args:
        mpn: Manufacturer Part Number of the product.
        vendor_name: Display name of the vendor (e.g., "Scorptec Computers").
        found: Whether the product was found at this vendor.
        price: Product price in AUD, or None if not found.

    Returns:
        None
    """
    if not found or price is None:
        return

    # Get the latest price for this MPN and vendor
    price_history = db.get_price_history(mpn, vendor_name)

    if not price_history:
        # No previous record, add new price
        db.add_price(mpn, vendor_name, price, datetime.now())
    else:
        # Check if price has changed
        latest_price = price_history[0]['price']
        if abs(latest_price - price) > 0.01:  # Allow for small floating point differences
            # Price changed, add new record
            db.add_price(mpn, vendor_name, price, datetime.now())
        else:
            # Price same, update timestamp of existing record
            db.update_price_timestamp(mpn, vendor_name, datetime.now())


def render_custom_metric(label, value, border_color="#1E88E5"):
    """
    Render a custom styled metric card.

    Creates a visually appealing metric display with custom styling including
    colored top border, shadow effects, and centered text.

    Args:
        label: The metric label/description to display.
        value: The metric value to display.
        border_color: Hex color code for the top border (default: blue #1E88E5).

    Returns:
        None: Renders directly to Streamlit UI.
    """
    st.markdown(f"""
        <div class="metric-card" style="border-top-color: {border_color};">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
    """, unsafe_allow_html=True)


# Page configuration
st.set_page_config(page_title="Price Scout", page_icon="💻", layout="wide")

# Custom CSS for high-contrast dashboard elements
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    /* Custom Card Design */
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        border-top: 5px solid #1E88E5;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-label { font-size: 0.9rem; color: #555; font-weight: 600; text-transform: uppercase; }
    .metric-value { font-size: 1.8rem; color: #111; font-weight: 800; }
    </style>
    """, unsafe_allow_html=True)

st.title("💻 Computer Parts Price Scout")
st.divider()

tab_single, tab_batch, tab_analytics = st.tabs(["🔍 Single MPN Query", "📁 CSV Batch Processing", "📊 Analytics"])

# TAB 1: SINGLE MPN QUERY
with tab_single:
    col_input, col_mode = st.columns([2, 2])
    with col_input:
        mpn_input = st.text_input("Enter MPN:", placeholder="e.g. 12400F")
    with col_mode:
        scrape_mode = st.radio(
            "Scrape Mode:",
            options=["Fast", "More Info"],
            horizontal=True,
            help="Fast: HTTP + Playwright fallback (no stock/condition). More Info: Playwright only (slower, includes stock/condition)."
        )

    if st.button("Fetch Prices", type="primary") and mpn_input:
        if scrape_mode == "Fast":
            with st.spinner(f"Searching {mpn_input} (Fast mode)..."):
                results = asyncio.run(scrape_mpn_single(mpn_input.strip(), False))
        else:
            with st.spinner(f"Searching {mpn_input} (More Info mode - this may take longer)..."):
                results = asyncio.run(scrape_mpn_single(mpn_input.strip(), True))

        # Process and save results to database
        for res in results:
            vendor_display_name = vendor_names.get(res.vendor_id, res.vendor_id)
            process_and_save_result(
                mpn=mpn_input.strip(),
                vendor_name=vendor_display_name,
                found=res.found,
                price=float(res.price) if res.price else None
            )

        # Build dataframe based on mode
        if scrape_mode == "Fast":
            df_single = pd.DataFrame([{
                "Vendor": vendor_names.get(res.vendor_id, res.vendor_id),
                "Price": float(res.price) if res.price else None,
                "Found": "✅" if res.found else "❌",
                "URL": str(res.url) if res.url else None
            } for res in results])

            st.dataframe(
                df_single,
                column_config={
                    "Price": st.column_config.NumberColumn(format="$%.2f"),
                    "URL": st.column_config.LinkColumn(label="Link", display_text="Link")
                },
                width='stretch',
                hide_index=True
            )
        else:
            df_single = pd.DataFrame([{
                "Vendor": vendor_names.get(res.vendor_id, res.vendor_id),
                "Price": float(res.price) if res.price else None,
                "Found": "✅" if res.found else "❌",
                "In Stock": "✅" if res.in_stock else "❌",
                "Condition": res.condition if res.found else None,
                "URL": str(res.url) if res.url else None
            } for res in results])

            st.dataframe(
                df_single,
                column_config={
                    "Price": st.column_config.NumberColumn(format="$%.2f"),
                    "URL": st.column_config.LinkColumn(label="Link", display_text="Link")
                },
                width='stretch',
                hide_index=True
            )

# TAB 2: CSV BATCH PROCESSING
with tab_batch:
    st.markdown("### 📄 Upload & Manage Batch")
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])

    if uploaded_file is not None:
        if 'mpn_list' not in st.session_state:
            try:
                content = uploaded_file.read().decode('utf-8')
                df_upload = pd.read_csv(StringIO(content))
                col_to_use = next((c for c in ['mpn', 'MPN'] if c in df_upload.columns), None)

                if col_to_use:
                    st.session_state.mpn_list = df_upload[[col_to_use]].dropna().rename(
                        columns={col_to_use: 'MPN To Process'}
                    )
                else:
                    st.error("❌ CSV must contain the 'mpn' or 'MPN' column")
                    st.stop()
            except Exception as e:
                st.error(f"Error: {e}")

        if 'mpn_list' in st.session_state:
            edited_df = st.data_editor(
                st.session_state.mpn_list,
                width='stretch',
                num_rows="dynamic",
                key="mpn_editor"
            )
            st.session_state.mpn_list = edited_df
            mpns_to_scan = edited_df['MPN To Process'].tolist()

            if st.button("🚀 Start Batch Search", type="primary"):
                progress_bar = st.progress(0)
                all_results = []
                successful_count = 0
                start_time = time.time()

                for i, mpn in enumerate(mpns_to_scan):
                    progress_bar.progress((i + 1) / len(mpns_to_scan))
                    results = asyncio.run(scrape_mpn_single(mpn))

                    # Process and save results to database
                    for res in results:
                        vendor_display_name = vendor_names.get(res.vendor_id, res.vendor_id)
                        process_and_save_result(
                            mpn=mpn.strip(),
                            vendor_name=vendor_display_name,
                            found=res.found,
                            price=float(res.price) if res.price else None
                        )

                    mpn_result = {'MPN': mpn}
                    prices = [float(res.price) for res in results if res.price]
                    lowest_price = min(prices) if prices else None

                    for res in results:
                        mpn_result[f'{vendor_names[res.vendor_id]} Price'] = (
                            float(res.price) if res.price else None
                        )

                    mpn_result['Best Price'] = lowest_price
                    if lowest_price:
                        successful_count += 1
                    all_results.append(mpn_result)

                elapsed_time = time.time() - start_time
                success_rate = (successful_count / len(mpns_to_scan) * 100)

                # Processing insights summary dashboard
                st.divider()
                st.subheader("📊 Processing Insights")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    render_custom_metric("Total Items", len(mpns_to_scan), "#1E88E5")
                with c2:
                    render_custom_metric("Items Found", successful_count, "#43A047")
                with c3:
                    rate_color = "#43A047" if success_rate > 80 else "#FB8C00"
                    render_custom_metric("Success Rate", f"{success_rate:.1f}%", rate_color)
                with c4:
                    render_custom_metric("Time Taken", f"{elapsed_time:.1f}s", "#757575")

                # Results table with best price highlighting
                df_final = pd.DataFrame(all_results)

                # Reorder to put critical info at the front
                main_cols = ['MPN', 'Best Price']
                other_cols = [c for c in df_final.columns if c not in main_cols]
                df_final = df_final[main_cols + other_cols]

                def highlight_best_price(row):
                    """Highlight the best price in each row with green background."""
                    styles = []
                    for col in row.index:
                        # Only apply to vendor price columns
                        if col.endswith('Price') and row[col] == row.get('Best Price'):
                            styles.append('background-color: #A7F3D0; color: #064E3B; font-weight: bold')
                        else:
                            styles.append('')  # default
                    return styles

                st.markdown("### 📋 Comparative Results")
                st.dataframe(
                    df_final.style.apply(highlight_best_price, axis=1)
                            .format(precision=2, na_rep="-",
                                    subset=[c for c in df_final.columns if 'price' in c.lower()]),
                    width='stretch'
                )

                st.download_button(
                    "📥 Export Results",
                    df_final.to_csv(index=False),
                    "results.csv",
                    "text/csv"
                )

# TAB 3: ANALYTICS
with tab_analytics:
    st.markdown("### 📈 Price Analytics & Trends")

    # Get all MPNs with price data
    available_mpns = db.get_all_mpns_with_prices()

    if not available_mpns:
        st.info("📭 No price data available yet. Search for some products first to see analytics!")
    else:
        # MPN selector
        selected_mpn = st.selectbox(
            "Select MPN to analyze:",
            options=available_mpns,
            help="Choose a product to view its price trends and statistics"
        )

        if selected_mpn:
            st.divider()

            # Get analytics data
            price_trends = db.get_price_trends_by_mpn(selected_mpn)
            avg_data = db.get_average_prices_by_mpn(selected_mpn)

            # Section 1: Price Trends Chart
            st.markdown(f"#### 📊 Price Trends for {selected_mpn}")

            if price_trends:
                # Prepare data for line chart
                chart_data = []
                for vendor, prices in price_trends.items():
                    for price_point in prices:
                        chart_data.append({
                            'Date': pd.to_datetime(price_point['date']),
                            'Price': price_point['price'],
                            'Vendor': vendor
                        })

                df_trends = pd.DataFrame(chart_data)

                # Create interactive line chart with visible markers using Plotly
                fig = go.Figure()

                # Define colors for different vendors
                colors = px.colors.qualitative.Set2

                # Add a line for each vendor
                for idx, vendor in enumerate(df_trends['Vendor'].unique()):
                    vendor_data = df_trends[df_trends['Vendor'] == vendor].sort_values('Date')

                    fig.add_trace(go.Scatter(
                        x=vendor_data['Date'],
                        y=vendor_data['Price'],
                        mode='lines+markers',  # Show both lines and markers
                        name=vendor,
                        line=dict(width=3, color=colors[idx % len(colors)]),
                        marker=dict(size=8, symbol='circle'),
                        hovertemplate='<b>%{fullData.name}</b><br>' +
                                      'Date: %{x|%Y-%m-%d %H:%M}<br>' +
                                      'Price: $%{y:.2f}<br>' +
                                      '<extra></extra>'
                    ))

                # Update layout for better appearance
                fig.update_layout(
                    height=450,
                    hovermode='closest',
                    xaxis=dict(
                        title='Date',
                        showgrid=True,
                        gridcolor='rgba(128,128,128,0.2)'
                    ),
                    yaxis=dict(
                        title='Price ($)',
                        showgrid=True,
                        gridcolor='rgba(128,128,128,0.2)'
                    ),
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.02,
                        xanchor='right',
                        x=1
                    ),
                    plot_bgcolor='white',
                    margin=dict(l=0, r=0, t=40, b=0)
                )

                # Display the chart
                st.plotly_chart(fig, width='stretch')

                # Show summary statistics
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("##### 📍 Current Prices")
                    latest_prices = []
                    for vendor, prices in price_trends.items():
                        if prices:
                            latest = prices[-1]
                            latest_prices.append({
                                'Vendor': vendor,
                                'Current Price': f"${latest['price']:.2f}",
                                'Last Updated': pd.to_datetime(latest['date']).strftime('%Y-%m-%d %H:%M')
                            })

                    df_latest = pd.DataFrame(latest_prices)
                    st.dataframe(df_latest, hide_index=True, width='stretch')

                with col2:
                    st.markdown("##### 📉 Price Range by Vendor")
                    price_ranges = []
                    for vendor, prices in price_trends.items():
                        if prices:
                            vendor_prices = [p['price'] for p in prices]
                            price_ranges.append({
                                'Vendor': vendor,
                                'Min': f"${min(vendor_prices):.2f}",
                                'Max': f"${max(vendor_prices):.2f}",
                                'Range': f"${max(vendor_prices) - min(vendor_prices):.2f}"
                            })

                    df_ranges = pd.DataFrame(price_ranges)
                    st.dataframe(df_ranges, hide_index=True, width='stretch')

            st.divider()

            # Section 2: Average Prices
            st.markdown(f"#### 💰 Average Price Analysis for {selected_mpn}")

            if avg_data['overall_avg']:
                # Display overall average with custom metric
                c1, c2, c3 = st.columns(3)
                with c1:
                    render_custom_metric(
                        "Overall Average Price",
                        f"${avg_data['overall_avg']:.2f}",
                        "#7C3AED"
                    )

                # Find cheapest and most expensive vendor on average
                if avg_data['vendor_avgs']:
                    cheapest = avg_data['vendor_avgs'][0]
                    most_expensive = avg_data['vendor_avgs'][-1]

                    with c2:
                        render_custom_metric(
                            "Cheapest (Avg)",
                            f"{cheapest['vendor_name']}: ${cheapest['avg_price']:.2f}",
                            "#10B981"
                        )

                    with c3:
                        render_custom_metric(
                            "Most Expensive (Avg)",
                            f"{most_expensive['vendor_name']}: ${most_expensive['avg_price']:.2f}",
                            "#EF4444"
                        )

                st.markdown("")  # Add spacing

                # Display vendor averages table and chart side by side
                col_table, col_chart = st.columns([1, 2])

                with col_table:
                    st.markdown("##### 📊 Average Prices by Vendor")
                    df_avg = pd.DataFrame(avg_data['vendor_avgs'])
                    df_avg['avg_price'] = df_avg['avg_price'].apply(lambda x: f"${x:.2f}")
                    df_avg.columns = ['Vendor', 'Average Price', 'Data Points']

                    st.dataframe(
                        df_avg,
                        hide_index=True,
                        width='stretch',
                        height=350
                    )

                with col_chart:
                    st.markdown("##### 📊 Average Price Comparison")
                    df_bar = pd.DataFrame(avg_data['vendor_avgs'])
                    df_bar['avg_price_num'] = df_bar['avg_price']
                    df_bar = df_bar.set_index('vendor_name')
                    st.bar_chart(df_bar['avg_price_num'], width='stretch', height=350)
            else:
                st.warning("No price data available for this MPN yet.")
