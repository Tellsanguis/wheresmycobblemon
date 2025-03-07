#!/usr/bin/env python3
import os
import json
import pandas as pd
import argparse
from openpyxl.styles import Alignment

# Fonction pour formater les valeurs booléennes de façon cohérente
def format_bool(val):
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, str) and val.lower() in ["true", "false"]:
        return val.lower()
    return val

# Extrait les données de spawn de Pokémon à partir d'un fichier JSON
def extract_spawn_data(json_file_path):
    rows = []
    try:
        # Ouvre et charge le fichier JSON
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Vérifie si le fichier contient des données de spawn
        if "spawns" in data:
            # Traite chaque entrée de spawn individuellement
            for spawn in data["spawns"]:
                pokemon = spawn.get("pokemon", "")
                bucket = spawn.get("bucket", "")
                condition = spawn.get("condition", {})
                
                # Extrait les différentes conditions de spawn
                # Transforme les listes en chaînes séparées par des virgules
                dimensions = ", ".join(condition.get("dimensions", []))
                biomes = ", ".join(condition.get("biomes", []))
                structures = ", ".join(condition.get("structures", []))
                moon_phase = condition.get("moonPhase", "")
                can_see_sky = format_bool(condition.get("canSeeSky", ""))
                
                # Coordonnées limites
                min_x = condition.get("minX", "")
                min_y = condition.get("minY", "")
                min_z = condition.get("minZ", "")
                max_x = condition.get("maxX", "")
                max_y = condition.get("maxY", "")
                max_z = condition.get("maxZ", "")
                
                # Conditions de luminosité
                min_light = condition.get("minLight", "")
                max_light = condition.get("maxLight", "")
                min_sky_light = condition.get("minSkyLight", "")
                max_sky_light = condition.get("maxSkyLight", "")
                
                # Conditions temporelles et météorologiques
                time_range = condition.get("timeRange", "")
                is_raining = format_bool(condition.get("isRaining", ""))
                is_thundering = format_bool(condition.get("isThundering", ""))
                is_slime_chunk = format_bool(condition.get("isSlimeChunk", ""))
                
                # Conditions d'étiquettes
                labels = ", ".join(condition.get("labels", []))
                label_mode = condition.get("labelMode", "")
                
                # Dimensions physiques
                min_width = condition.get("minWidth", "")
                max_width = condition.get("maxWidth", "")
                min_height = condition.get("minHeight", "")
                max_height = condition.get("maxHeight", "")
                
                # Blocs environnants nécessaires
                needed_nearby_blocks = ", ".join(condition.get("neededNearbyBlocks", []))
                needed_base_blocks = ", ".join(condition.get("neededBaseBlocks", []))
                
                # Conditions de profondeur et de fluide
                min_depth = condition.get("minDepth", "")
                max_depth = condition.get("maxDepth", "")
                fluid_is_source = format_bool(condition.get("fluidIsSource", ""))
                fluid_block = condition.get("fluidBlock", "")
                key_item = condition.get("key_item", "")
                
                # Traitement des exigences de pierre spécifiques
                stone_requirements = []
                for key, value in condition.items():
                    if key.endswith("_stone_requirement"):
                        stone_type = key.replace("_stone_requirement", "")
                        stone_requirements.append(f"{stone_type}: {value}")
                stone_requirements_str = ", ".join(stone_requirements)
                
                # Traitement des conditions d'équipe Pokémon
                custom_team = ""
                if "custom_pokemons_in_team" in condition:
                    team_list = condition.get("custom_pokemons_in_team", [])
                    formatted_team = []
                    for entry in team_list:
                        species = entry.get("species", "")
                        count = entry.get("count", "")
                        if species:
                            formatted_team.append(f"{species}: {count}")
                    custom_team = ", ".join(formatted_team)
                
                # Ajoute toutes les données extraites à la liste des lignes
                rows.append({
                    "Pokemon": pokemon,
                    "Bucket": bucket,
                    "Dimensions": dimensions,
                    "Biomes": biomes,
                    "Structures": structures,
                    "Moon Phase": moon_phase,
                    "Can See Sky": can_see_sky,
                    "Min X": min_x,
                    "Min Y": min_y,
                    "Min Z": min_z,
                    "Max X": max_x,
                    "Max Y": max_y,
                    "Max Z": max_z,
                    "Min Light": min_light,
                    "Max Light": max_light,
                    "Min Sky Light": min_sky_light,
                    "Max Sky Light": max_sky_light,
                    "Time Range": time_range,
                    "Is Raining": is_raining,
                    "Is Thundering": is_thundering,
                    "Is Slime Chunk": is_slime_chunk,
                    "Labels": labels,
                    "Label Mode": label_mode,
                    "Min Width": min_width,
                    "Max Width": max_width,
                    "Min Height": min_height,
                    "Max Height": max_height,
                    "Needed Nearby Blocks": needed_nearby_blocks,
                    "Needed Base Blocks": needed_base_blocks,
                    "Min Depth": min_depth,
                    "Max Depth": max_depth,
                    "Fluid Is Source": fluid_is_source,
                    "Fluid Block": fluid_block,
                    "Key Item": key_item,
                    "Stone Requirements": stone_requirements_str,
                    "Custom Pokemons In Team": custom_team
                })
    except Exception as e:
        print(f"Erreur lors du traitement de {json_file_path}: {e}")
    return rows

def main():
    # Configuration du parseur d'arguments pour les options en ligne de commande
    parser = argparse.ArgumentParser(
        description="Extrait les données de spawn depuis les fichiers JSON dans 'spawn_pool_world' et ajoute (en option) les données d'un tableur additionnel."
    )
    parser.add_argument("target_dir", help="Dossier cible où chercher les fichiers JSON")
    parser.add_argument("--output", default="spawn_data.xlsx", help="Nom du fichier Excel de sortie")
    parser.add_argument("--additional", help="Chemin vers le fichier Excel additionnel (Cobblemon) (colonnes B:S)")
    args = parser.parse_args()

    # Liste des colonnes qui seront présentes dans le fichier de sortie
    base_columns = [
        "Pokemon", "Bucket", "Dimensions", "Biomes", "Structures", "Moon Phase", "Can See Sky",
        "Min X", "Min Y", "Min Z", "Max X", "Max Y", "Max Z",
        "Min Light", "Max Light", "Min Sky Light", "Max Sky Light", "Time Range",
        "Is Raining", "Is Thundering", "Is Slime Chunk", "Labels", "Label Mode",
        "Min Width", "Max Width", "Min Height", "Max Height",
        "Needed Nearby Blocks", "Needed Base Blocks", "Min Depth", "Max Depth",
        "Fluid Is Source", "Fluid Block", "Key Item", "Stone Requirements", "Custom Pokemons In Team"
    ]
    
    # Parcours récursif des répertoires pour trouver les fichiers JSON
    all_rows = []
    for root, dirs, files in os.walk(args.target_dir):
        if os.path.basename(root) == "spawn_pool_world":
            for file in files:
                if file.lower().endswith(".json"):
                    json_file_path = os.path.join(root, file)
                    rows = extract_spawn_data(json_file_path)
                    all_rows.extend(rows)
    
    # Création du DataFrame pandas avec les données extraites
    df_config = pd.DataFrame(all_rows, columns=base_columns)
    
    # Traitement du fichier Excel additionnel si spécifié
    if args.additional:
        try:
            # Lecture du fichier Excel additionnel, en se limitant aux colonnes B à S
            df_additional = pd.read_excel(args.additional, usecols="B:S")
            print("Colonnes du tableur additionnel lues :", df_additional.columns.tolist())
            
            # Mappage des noms de colonnes pour correspondre à notre format
            mapping = {
                "Pokémon": "Pokemon",
                "Bucket": "Bucket",
                "Biomes": "Biomes",
                "Time": "Time Range",
                "skyLightMin": "Min Sky Light",
                "skyLightMax": "Max Sky Light",
                "canSeeSky": "Can See Sky"
            }
            df_additional.rename(columns=mapping, inplace=True)
            
            # Sélection des colonnes qui nous intéressent
            cols_to_keep = ["Pokemon"] + [v for k, v in mapping.items() if v != "Pokemon"]
            df_additional = df_additional[[col for col in cols_to_keep if col in df_additional.columns]]
            
            # Transformation des données additionnelles au format attendu
            additional_rows = []
            for idx, row in df_additional.iterrows():
                new_row = {col: "" for col in base_columns}
                for col in cols_to_keep:
                    if col in row and pd.notna(row[col]):
                        new_row[col] = row[col]
                additional_rows.append(new_row)
            df_additional_transformed = pd.DataFrame(additional_rows, columns=base_columns)
            
            # Concaténation des données extraites et additionnelles
            df_final = pd.concat([df_config, df_additional_transformed], ignore_index=True)
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier additionnel {args.additional}: {e}")
            df_final = df_config
    else:
        df_final = df_config

    # Écriture des données dans un fichier Excel avec formatage
    with pd.ExcelWriter(args.output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name="Spawns")
        worksheet = writer.sheets["Spawns"]
        # Ajout d'un filtre automatique
        worksheet.auto_filter.ref = worksheet.dimensions
        # Application du retour à la ligne automatique pour toutes les cellules
        for row in worksheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(wrapText=True)
    print(f"Les données ont été extraites et sauvegardées dans {args.output}")

if __name__ == "__main__":
    main()
