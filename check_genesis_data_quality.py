import pandas as pd

df = pd.read_csv("genesis_history_scores.csv")

# Check for missing rounds (Total vs 1,2,3,4)
print("Rounds distribution:")
print(df["Round"].value_counts())

# Check yardage variation within a year
# If yardage is constant for all holes, that's expected.
# If yardage is constant for a specific hole across all rounds (or total), that's also expected.
# But we should check if ESPN provides yardage per hole.
print("\nYardage check:")
# Group by Year and Source
for (year, source), group in df.groupby(["Year", "Source"]):
    print(f"\n{year} ({source}):")
    # Check if we have round data
    rounds = group["Round"].unique()
    print(f"  Rounds: {rounds}")

    # Check if yardage varies per hole (sanity check)
    print(f"  Unique Yardages: {group['Yards'].nunique()}")

    # If source is ESPN, we know it's 'Total'. Does ESPN give hole-specific yardage?
    # Yes, the table had a Yardage column.

    # But does the yardage change year over year?
    # Group by Hole and check yardage
    # But for a single year/source, each hole has one yardage.
