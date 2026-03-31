from orchestration.fis.graph import build_fis_graph

# Example stub showing how you would import the sis and fis compiled graphs
# from orchestration.sis.graph import build_sis_graph

def run():
    fis_graph = build_fis_graph()
    print("FIS graph compiled successfully!")

if __name__ == "__main__":
    run()