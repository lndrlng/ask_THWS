# visualize_triplets_app.py
import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
from pyvis.network import Network
import os
import io
import matplotlib # Explicit import can help pyvis/nx find it
import seaborn # Explicit import can help pyvis/nx find it


# --- Page Config ---
st.set_page_config(layout="wide", page_title="Triplet Visualizer")

st.title("📊 Interactive Triplet Visualizer")

# --- File Upload ---
uploaded_file = st.sidebar.file_uploader("Upload your Triplet JSON file", type=["json"])

# --- Default Configuration ---
DEFAULT_TOP_N_RELATIONS = 20
DEFAULT_NETWORK_NODE_LIMIT = 150
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

# --- Load Data ---
# Use Streamlit's caching to avoid reloading data on every interaction
@st.cache_data
def load_data(file_content_bytes):
    try:
        # Read the file content
        stringio = io.StringIO(file_content_bytes.decode("utf-8"))
        triplets_data = json.load(stringio)
        df = pd.DataFrame(triplets_data)

        # Basic validation and cleaning
        required_cols = ['subject', 'subject_type', 'relation', 'object', 'object_type', 'confidence', 'origin']
        if not all(col in df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df.columns]
            st.error(f"Error: Input file is missing required columns: {missing}")
            return pd.DataFrame() # Return empty DataFrame

        df['subject_type'] = df['subject_type'].fillna('Unknown')
        df['object_type'] = df['object_type'].fillna('Unknown')
        df['origin'] = df['origin'].fillna('Unknown')
        df['confidence'] = pd.to_numeric(df['confidence'], errors='coerce').fillna(0.0)

        return df
    except json.JSONDecodeError:
        st.error(f"Error: Could not decode JSON from the uploaded file. Is it a valid JSON?")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred during loading: {e}")
        return pd.DataFrame()

df = pd.DataFrame() # Initialize empty DataFrame
if uploaded_file is not None:
    # Pass the file content bytes to the cached function
    df = load_data(uploaded_file.getvalue())
else:
    st.info("Please upload a triplet JSON file to begin.")

# --- Sidebar Options ---
st.sidebar.header("Display Options")

show_subject_types = st.sidebar.checkbox("Subject Type Distribution", True)
show_object_types = st.sidebar.checkbox("Object Type Distribution", True)
show_relations = st.sidebar.checkbox("Top Relations", True)
show_confidence = st.sidebar.checkbox("Confidence Distribution", True)
show_origin = st.sidebar.checkbox("Origin Distribution", True)
show_data_table = st.sidebar.checkbox("Show Data Table", False)

st.sidebar.header("Network Graph Options")
generate_graph_button = st.sidebar.button("Generate Network Graph (HTML)")
network_confidence_threshold = st.sidebar.slider(
    "Min Confidence for Network Graph", 0.0, 1.0, DEFAULT_CONFIDENCE_THRESHOLD, 0.05
)
network_node_limit = st.sidebar.number_input(
    "Max Nodes in Network Graph", min_value=10, value=DEFAULT_NETWORK_NODE_LIMIT, step=10
)


# --- Main Panel ---
if not df.empty:
    if uploaded_file:
        st.success(f"Successfully loaded {len(df)} triplets from '{uploaded_file.name}'.")

    # Create columns for layout
    col1, col2 = st.columns(2)

    # --- Static Plots (using Plotly for interactivity) ---
    if show_subject_types:
        with col1:
            st.subheader("Subject Type Distribution")
            subject_type_counts = df['subject_type'].value_counts().reset_index()
            subject_type_counts.columns = ['Subject Type', 'Count']
            fig = px.bar(subject_type_counts, x='Subject Type', y='Count', title="Subject Types",
                         color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    if show_object_types:
        with col2:
            st.subheader("Object Type Distribution")
            object_type_counts = df['object_type'].value_counts().reset_index()
            object_type_counts.columns = ['Object Type', 'Count']
            fig = px.bar(object_type_counts, x='Object Type', y='Count', title="Object Types",
                         color_discrete_sequence=px.colors.qualitative.Pastel1)
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    if show_relations:
        with col1:
            st.subheader(f"Top {DEFAULT_TOP_N_RELATIONS} Relations")
            relation_counts = df['relation'].value_counts().nlargest(DEFAULT_TOP_N_RELATIONS).reset_index()
            relation_counts.columns = ['Relation', 'Count']
            fig = px.bar(relation_counts, x='Count', y='Relation', title="Most Frequent Relations",
                         orientation='h', color_discrete_sequence=px.colors.qualitative.Antique)
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)

    if show_confidence:
        with col2:
            st.subheader("Confidence Score Distribution")
            fig = px.histogram(df, x="confidence", title="Confidence Scores", nbins=30,
                               color_discrete_sequence=px.colors.qualitative.Bold)
            st.plotly_chart(fig, use_container_width=True)

    if show_origin:
        # Decide column based on whether relations chart is shown
        target_col = col2 if show_relations else col1
        with target_col:
            st.subheader("Origin Distribution")
            origin_counts = df['origin'].value_counts().reset_index()
            origin_counts.columns = ['Origin', 'Count']
            fig = px.pie(origin_counts, values='Count', names='Origin', title="Triplet Origin",
                         color_discrete_sequence=px.colors.qualitative.G10)
            st.plotly_chart(fig, use_container_width=True)

    if show_data_table:
        st.subheader("Raw Triplet Data")
        # Display limited rows for performance in browser
        st.dataframe(df.head(1000))
        if len(df) > 1000:
            st.caption(f"Displaying first 1000 rows out of {len(df)} total.")


    # --- Network Graph Generation Logic ---
    if generate_graph_button:
        st.info("Generating network graph... Please wait.")
        output_filename = 'triplet_network_graph.html'
        try:
            # Filter data for the graph
            df_graph = df[df['confidence'] >= network_confidence_threshold].copy()
            st.write(f"Using {len(df_graph)} triplets for the graph (Confidence >= {network_confidence_threshold}).")

            if not df_graph.empty:
                # Create a directed graph
                G = nx.DiGraph()

                # Get node types
                node_type_map = pd.concat([
                    df_graph[['subject', 'subject_type']].rename(columns={'subject': 'node', 'subject_type': 'type'}),
                    df_graph[['object', 'object_type']].rename(columns={'object': 'node', 'object_type': 'type'})
                ]).drop_duplicates(subset='node').set_index('node')['type'].to_dict()

                # Identify nodes and limit if necessary
                nodes = set(df_graph['subject']).union(set(df_graph['object']))
                if len(nodes) > network_node_limit:
                    st.warning(f"Too many nodes ({len(nodes)}). Limiting graph to most frequent {network_node_limit} nodes.")
                    node_counts = pd.concat([df_graph['subject'], df_graph['object']]).value_counts()
                    top_nodes = set(node_counts.nlargest(network_node_limit).index)
                    # Filter edges to only include those connecting top nodes
                    df_graph = df_graph[df_graph['subject'].isin(top_nodes) & df_graph['object'].isin(top_nodes)]
                    nodes = top_nodes # Update the node set

                # Add nodes with types and titles for hover info and grouping (colors)
                for node in nodes:
                    node_type = node_type_map.get(node, 'Unknown')
                    # Use shorter label if node name is too long? Optional.
                    # label = node if len(node) < 30 else node[:27] + "..."
                    label = node
                    G.add_node(node, label=label, title=f"{node}\nType: {node_type}", group=node_type)

                # Add edges with relations as labels/titles
                for _, row in df_graph.iterrows():
                    # Check if both nodes exist in our potentially limited node set
                    if row['subject'] in nodes and row['object'] in nodes:
                        G.add_edge(row['subject'], row['object'], label=row['relation'], title=f"{row['relation']} (Conf: {row['confidence']:.2f})")

                # Create a Pyvis network
                net = Network(notebook=False, directed=True, height='800px', width='100%', bgcolor='#FFFFFF', font_color='black')
                net.from_nx(G)

                # Add physics layout options for better interactivity and proximity visualization
                # Tuned gravitationalConstant and springLength for potentially better spacing
                net.set_options("""
                var options = {
                  "nodes": {"font": {"size": 10}},
                  "edges": {
                      "color": {"inherit": true},
                      "smooth": {"type": "continuous", "forceDirection": "none", "roundness": 0.5},
                      "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}}
                   },
                  "interaction": {"hover": true, "tooltipDelay": 200, "navigationButtons": true, "keyboard": true},
                  "physics": {
                    "enabled": true,
                    "barnesHut": {
                      "gravitationalConstant": -10000, "centralGravity": 0.1, "springLength": 150,
                      "springConstant": 0.04, "damping": 0.09, "avoidOverlap": 0.1
                    },
                    "maxVelocity": 50,
                    "minVelocity": 0.1,
                    "solver": "barnesHut",
                    "stabilization": {"enabled": true, "iterations": 1000, "updateInterval": 25}
                  }
                }
                """)

                # Save the interactive graph as HTML
                net.save_graph(output_filename)
                st.success(f"Network graph saved as '{output_filename}'. You can open this file in your browser.")

                # Provide download button
                with open(output_filename, "rb") as fp:
                    btn = st.download_button(
                        label="Download Network Graph (HTML)",
                        data=fp,
                        file_name=output_filename,
                        mime="text/html"
                    )

            else:
                st.warning(f"No triplets found with confidence >= {network_confidence_threshold}. Cannot generate graph.")

        except Exception as e:
            st.error(f"Failed to generate network graph: {e}")
            st.exception(e) # Show full traceback in the app for debugging


elif uploaded_file is None:
    st.sidebar.warning("Upload a file to see options and visualizations.")