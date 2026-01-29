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
    - Device Deal
    - PB Tech
    - Wired Zone
    - PLE Computers
    - Server Supply
    - eBay Australia
"""

import time
import asyncio
import pandas as pd
from io import StringIO
from datetime import datetime
from scraper import scrape_mpn_single, AsyncBatchScraper
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
    "cpl": "CPL",
    "devicedeal": "Device Deal",
    "pbtech": "PB Tech",
    "wiredzone": "Wired Zone",
    "ple": "PLE Computers",
    "serversupply": "Server Supply",
    "ebay_au": "eBay Australia",
    "amazon_au": "Amazon Australia"
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
        detailed = (scrape_mode == "More Info")
        status_placeholder = st.empty()
        table_placeholder = st.empty()
        all_results = []  # list of PriceResult

        def _build_df(results_so_far, is_detailed):
            if is_detailed:
                return pd.DataFrame([{
                    "Vendor": vendor_names.get(r.vendor_id, r.vendor_id),
                    "Price": float(r.price) if r.price else None,
                    "Found": "✅" if r.found else "❌",
                    "In Stock": "✅" if r.in_stock else "❌",
                    "Condition": r.condition if r.found else None,
                    "URL": str(r.url) if r.url else None,
                } for r in results_so_far])
            return pd.DataFrame([{
                "Vendor": vendor_names.get(r.vendor_id, r.vendor_id),
                "Price": float(r.price) if r.price else None,
                "Found": "✅" if r.found else "❌",
                "URL": str(r.url) if r.url else None,
            } for r in results_so_far])

        scraper_system = AsyncBatchScraper([mpn_input.strip()], detailed=detailed)
        total_vendors = len(scraper_system.scrapers)
        progress_state = {"count": 0}

        async def _stream():
            from models.models import PriceResult
            async for res_item in scraper_system.start():
                progress_state["count"] += 1
                result = res_item.get("result")
                vendor = res_item.get("vendor", "")
                if result is None:
                    result = PriceResult(
                        vendor_id=vendor.lower().replace(" ", "_"),
                        found=False,
                    )
                all_results.append(result)

                # Update live status
                found_count = sum(1 for r in all_results if r.found)
                status_placeholder.markdown(
                    f"**{progress_state['count']}/{total_vendors}** vendors done "
                    f"— **{found_count}** found"
                )

                # Rebuild and display table
                df = _build_df(all_results, detailed)
                table_placeholder.dataframe(
                    df,
                    column_config={
                        "Price": st.column_config.NumberColumn(format="$%.2f"),
                        "URL": st.column_config.LinkColumn(label="Link", display_text="Link"),
                    },
                    width="stretch",
                    hide_index=True,
                )

        asyncio.run(_stream())

        found_total = sum(1 for r in all_results if r.found)
        status_placeholder.markdown(
            f"**{total_vendors}/{total_vendors}** vendors done "
            f"— **{found_total}** found ✓"
        )

        # Save results to database
        for res in all_results:
            vendor_display_name = vendor_names.get(res.vendor_id, res.vendor_id)
            process_and_save_result(
                mpn=mpn_input.strip(),
                vendor_name=vendor_display_name,
                found=res.found,
                price=float(res.price) if res.price else None,
            )

# TAB 2: CSV BATCH PROCESSING
with tab_batch:
    st.markdown("### 📄 Upload & Manage Batch")
    batch_scrape_mode = st.radio(
        "Scrape Mode:",
        options=["Fast", "More Info"],
        horizontal=True,
        help="Fast uses HTTP scrapers for speed. More Info switches to Playwright-only scrapers to capture stock status and condition."
    )

    if batch_scrape_mode == "Fast":
        st.info("For full stock availability details choose More Info mode (slower).", icon="ℹ️")

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
                from models.models import PriceResult

                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Containers for real-time updates
                all_results_dict = {} # mpn -> {vendor: result}
                display_results_list = []
                vendor_rows = []
                
                start_time = time.time()
                detailed_batch = (batch_scrape_mode == "More Info")

                # Initialize Async Batch Scraper
                scraper_system = AsyncBatchScraper(mpns_to_scan, detailed=detailed_batch)
                
                total_expected_results = len(mpns_to_scan) * 16 # 16 vendors
                progress_state = {'received': 0}
                
                async def run_batch():
                    async for res_item in scraper_system.start():
                        progress_state['received'] += 1
                        results_received = progress_state['received']
                        mpn = res_item['mpn']
                        vendor = res_item['vendor']
                        result = res_item['result']
                        
                        # Update progress
                        progress = results_received / total_expected_results
                        progress_bar.progress(min(progress, 1.0))
                        status_text.text(f"Processing... {results_received}/{total_expected_results} checks completed.")
                        
                        # Save result
                        if mpn not in all_results_dict:
                            all_results_dict[mpn] = {}
                        all_results_dict[mpn][vendor] = result

                        if result:
                            # Process and save to DB immediately
                            vendor_display_name = vendor_names.get(result.vendor_id, result.vendor_id)
                            process_and_save_result(
                                mpn=mpn.strip(),
                                vendor_name=vendor_display_name,
                                found=result.found,
                                price=float(result.price) if result.price else None
                            )
                            
                            # Add to detailed rows
                            price_value = float(result.price) if result.price else None
                            vendor_rows.append({
                                'MPN': mpn,
                                'Vendor': vendor_display_name,
                                'Price': price_value,
                                'Found': "✅" if result.found else "❌",
                                'In Stock': "✅" if result.in_stock else ("❌" if result.in_stock is False else "N/A"),
                                'Condition': result.condition if result.condition else None,
                                'URL': str(result.url) if result.url else None
                            })

                asyncio.run(run_batch())
                
                # Post-processing for Display Matrix
                successful_count = 0
                all_results = []
                
                for mpn in mpns_to_scan:
                    mpn_data = all_results_dict.get(mpn, {})
                    
                    # Calculate best price
                    prices = []
                    for v_res in mpn_data.values():
                        if v_res and v_res.price:
                            prices.append(float(v_res.price))
                    lowest_price = min(prices) if prices else None
                    if lowest_price:
                        successful_count += 1
                        
                    # Build Row
                    mpn_result = {'MPN': mpn, 'Best Price': lowest_price}
                    display_result = {'MPN': mpn, 'Best Price': lowest_price}
                    
                    # Check all known vendors (even if missed/timed out)
                    current_scrapers = scraper_system.scrapers # Get list of (name, inst)
                    
                    for v_name, _ in current_scrapers:
                        res = mpn_data.get(v_name)
                        vendor_display_name = vendor_names.get(v_name.lower().replace(" ", "_"), v_name)
                        if not vendor_display_name: # Fallback
                             vendor_display_name = v_name

                        # For Detailed CSV
                        if res:
                             mpn_result[f'{vendor_display_name} Price'] = float(res.price) if res.price else None
                             mpn_result[f'{vendor_display_name} Status'] = "✅" if res.found else "❌"
                             if detailed_batch:
                                 stock_value = "✅ In Stock" if res.in_stock else ("❌ Out of Stock" if res.in_stock is False else "Unknown")
                                 mpn_result[f'{vendor_display_name} Stock'] = stock_value
                                 mpn_result[f'{vendor_display_name} Condition'] = res.condition or "Unknown"
                        else:
                             mpn_result[f'{vendor_display_name} Price'] = None
                             mpn_result[f'{vendor_display_name} Status'] = "—"

                        # For Display Matrix
                        if not res or not res.found or res.price is None:
                            display_val = "—"
                        else:
                            price_str = f"${float(res.price):.2f}"
                            if detailed_batch:
                                if res.in_stock is True:
                                    status_icon = "🟢"
                                elif res.in_stock is False:
                                    status_icon = "🔴"
                                else:
                                    status_icon = "❓"
                            else:
                                status_icon = ""
                            display_val = f"{price_str} {status_icon}".strip()
                        
                        display_result[vendor_display_name] = display_val
                        
                    all_results.append(mpn_result)
                    display_results_list.append(display_result)
                    
                status_text.text("Batch processing complete!")

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

                # --- UI DISPLAY: COMPACT MATRIX ---
                st.markdown("### 📋 Comparative Results")
                st.caption("🟢 In Stock | 🔴 Out of Stock | ❓ Unknown Status")
                
                df_display = pd.DataFrame(display_results_list)
                
                # Reorder columns: MPN, Best Price, then Vendors alphabetically
                if not df_display.empty:
                    cols = list(df_display.columns)
                    fixed_cols = ['MPN', 'Best Price']
                    vendor_cols = sorted([c for c in cols if c not in fixed_cols])
                    df_display = df_display[fixed_cols + vendor_cols]

                    def highlight_best_price_display(row):
                        """Highlight the best price in the display dataframe."""
                        styles = []
                        best_val = row.get('Best Price')
                        
                        for col in row.index:
                            cell_val = str(row[col])
                            # Check if this cell represents the best price
                            if col not in ['MPN', 'Best Price'] and best_val is not None:
                                # Extract numeric part from string "$100.00 🟢"
                                try:
                                    # Simple check: does the cell start with the formatted best price?
                                    if cell_val.startswith(f"${best_val:.2f}"):
                                        styles.append('background-color: #A7F3D0; color: #064E3B; font-weight: bold')
                                    else:
                                        styles.append('')
                                except:
                                    styles.append('')
                            else:
                                styles.append('')
                        return styles

                    st.dataframe(
                        df_display.style.apply(highlight_best_price_display, axis=1)
                                  .format(precision=2, subset=['Best Price'], na_rep="-"),
                        width='stretch',
                        hide_index=True
                    )
                else:
                    st.warning("No results to display.")

                # --- EXPORT SECTION ---
                col_exp1, col_exp2 = st.columns(2)
                
                # Prepare detailed CSV for export (keep all technical columns)
                df_export = pd.DataFrame(all_results)
                
                with col_exp1:
                    st.download_button(
                        "📥 Export Detailed Results (CSV)",
                        df_export.to_csv(index=False),
                        "results_detailed.csv",
                        "text/csv",
                        help="Includes separate columns for Price, Stock, Condition, and URLs."
                    )
                
                if vendor_rows:
                    df_vendor = pd.DataFrame(vendor_rows)
                    with col_exp2:
                         st.download_button(
                            "📥 Export Vendor Availability (CSV)",
                            df_vendor.to_csv(index=False),
                            "vendor_availability.csv",
                            "text/csv",
                            help="Long-format table with every found MPN/Vendor combination."
                        )
                    
                    with st.expander("View Raw Vendor Availability Data"):
                         st.dataframe(
                            df_vendor,
                            column_config={
                                "Price": st.column_config.NumberColumn(format="$%.2f"),
                                "URL": st.column_config.LinkColumn(label="Link", display_text="Link")
                            },
                            width='stretch',
                            hide_index=True
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
