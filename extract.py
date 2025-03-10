#!/usr/bin/env python3
import os
import json
import pandas as pd
import argparse
from openpyxl.styles import Alignment
import re

# Fonction pour formater les valeurs booléennes de façon cohérente
def format_bool(val):
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, str) and val.lower() in ["true", "false"]:
        return val.lower()
    return val

# Fonction pour charger et analyser le fichier biomes_tags.txt
def load_biome_tags(biome_tags_file):
    tag_to_biomes = {}  # Dictionnaire pour associer chaque tag à une liste de biomes
    valid_biomes = set()  # Ensemble pour stocker tous les biomes valides
    valid_tags = set()    # Ensemble pour stocker tous les tags valides
    
    try:
        with open(biome_tags_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # Trouver l'en-tête pour déterminer les positions des colonnes
            header_line = [line for line in lines if "Registry name" in line][0]
            registry_col_start = header_line.find("Registry name")
            tags_col_start = header_line.find("Tags")
            
            # Traiter chaque ligne de données
            for line in lines:
                # Ignorer les lignes d'en-tête ou sans contenu substantiel
                if "Registry name" in line or "---" in line or not line.strip():
                    continue
                
                # Extraire le nom du biome et ses tags s'ils existent
                if len(line) > tags_col_start:
                    registry_name = line[registry_col_start:tags_col_start].strip()
                    tags_text = line[tags_col_start:].strip()
                    
                    # Ajouter le biome à l'ensemble des biomes valides
                    valid_biomes.add(registry_name)
                    
                    # Si des tags sont présents
                    if tags_text:
                        # Diviser les tags et les nettoyer
                        tags = [tag.strip() for tag in tags_text.split(',')]
                        
                        # Pour chaque tag, ajouter ce biome à la liste correspondante
                        for tag in tags:
                            valid_tags.add(tag)
                            if tag.startswith('#'):
                                valid_tags.add(tag[1:])  # Version sans #
                            else:
                                valid_tags.add('#' + tag)  # Version avec #
                                
                            if tag not in tag_to_biomes:
                                tag_to_biomes[tag] = []
                            tag_to_biomes[tag].append(registry_name)
    except Exception as e:
        print(f"Erreur lors du chargement du fichier de tags de biomes {biome_tags_file}: {e}")
    
    return tag_to_biomes, valid_biomes, valid_tags

# Fonction pour résoudre un tag de biome en liste de biomes
def resolve_biome_tag(tag, tag_to_biomes, visited_tags=None):
    if visited_tags is None:
        visited_tags = set()
    
    # Éviter les boucles infinies
    if tag in visited_tags:
        return []
    
    visited_tags.add(tag)
    
    # Normaliser le format du tag en enlevant le préfixe # si présent
    normalized_tag = tag.lstrip('#')
    
    # Chercher une correspondance dans notre dictionnaire de tags
    resolved_biomes = []
    for db_tag, biomes in tag_to_biomes.items():
        # Comparer le tag normalisé avec les tags de la base de données
        if normalized_tag == db_tag or normalized_tag == db_tag.lstrip('#'):
            resolved_biomes.extend(biomes)
    
    # Si aucun biome résolu et le tag commence par "cobblemon:is_", essayer avec "minecraft:is_"
    if not resolved_biomes and "cobblemon:is_" in normalized_tag:
        alternate_tag = normalized_tag.replace("cobblemon:is_", "minecraft:is_")
        
        # Chercher avec le tag alternatif
        for db_tag, biomes in tag_to_biomes.items():
            if alternate_tag == db_tag or alternate_tag == db_tag.lstrip('#'):
                resolved_biomes.extend(biomes)
    
    return resolved_biomes

# Fonction pour résoudre tous les tags de biomes dans une chaîne (avec validation stricte)
def resolve_biome_tags_in_string(biomes_str, tag_to_biomes, valid_biomes, valid_tags):
    if not biomes_str:
        return ""
    
    # Diviser la chaîne en biomes individuels
    biomes = [b.strip() for b in biomes_str.split(',')]
    all_resolved_biomes = []
    
    for biome in biomes:
        # Si c'est un tag (commence par # ou contient "is_")
        if biome.startswith('#') or ":is_" in biome:
            # S'assurer que le biome a le préfixe #
            if not biome.startswith('#'):
                biome = '#' + biome
                
            # Essayer de résoudre le tag
            resolved = resolve_biome_tag(biome, tag_to_biomes)
            if resolved:
                all_resolved_biomes.extend(resolved)
            else:
                # Si le tag concerne cobblemon:is_, essayer de le remplacer par minecraft:is_
                if "cobblemon:is_" in biome:
                    minecraft_tag = biome.replace("cobblemon:is_", "minecraft:is_")
                    resolved_minecraft = resolve_biome_tag(minecraft_tag, tag_to_biomes)
                    if resolved_minecraft:
                        all_resolved_biomes.extend(resolved_minecraft)
                # Si c'est un tag non résolu qui n'est pas reconnu, l'ignorer
        else:
            # Ce n'est PAS un tag mais un biome direct (minecraft:taiga, etc.)
            # Vérifier s'il est dans valid_biomes ou s'il s'agit d'un biome standard
            if biome in valid_biomes or "minecraft:" in biome:
                all_resolved_biomes.append(biome)
    
    # Éliminer les doublons et joindre les biomes en une chaîne
    return ', '.join(sorted(set(all_resolved_biomes)))

# Fonction pour résoudre les tags de biomes dans une chaîne sans filtrer les biomes inconnus
# Utilisée pour le fichier additionnel uniquement
def resolve_biome_tags_in_string_lenient(biomes_str, tag_to_biomes):
    if not biomes_str:
        return ""
    
    # Diviser la chaîne en biomes individuels
    biomes = [b.strip() for b in biomes_str.split(',')]
    all_resolved_biomes = []
    preserved_biomes = []
    
    for biome in biomes:
        # Si c'est un tag (commence par # ou contient "is_")
        if biome.startswith('#') or ":is_" in biome:
            # S'assurer que le biome a le préfixe #
            if not biome.startswith('#'):
                biome = '#' + biome
                
            # Essayer de résoudre le tag
            resolved = resolve_biome_tag(biome, tag_to_biomes)
            if resolved:
                all_resolved_biomes.extend(resolved)
            else:
                # Si le tag concerne cobblemon:is_, essayer de le remplacer par minecraft:is_
                if "cobblemon:is_" in biome:
                    minecraft_tag = biome.replace("cobblemon:is_", "minecraft:is_")
                    resolved_minecraft = resolve_biome_tag(minecraft_tag, tag_to_biomes)
                    if resolved_minecraft:
                        all_resolved_biomes.extend(resolved_minecraft)
                    else:
                        # Garder le tag original s'il ne peut pas être résolu
                        preserved_biomes.append(biome)
                else:
                    # Conserver tous les autres tags non résolus
                    preserved_biomes.append(biome)
        else:
            # Ce n'est pas un tag, le conserver tel quel
            preserved_biomes.append(biome)
    
    # Combiner les biomes résolus et ceux conservés
    combined_biomes = all_resolved_biomes + preserved_biomes
    
    # Éliminer les doublons et joindre les biomes en une chaîne
    return ', '.join(sorted(set(combined_biomes)))

# Fonction pour analyser les conditions spéciales de spawn
def parse_special_conditions(special_conditions):
    # Dictionnaire pour stocker les informations extraites
    extracted_info = {
        "Needed Nearby Blocks": [],
        "Needed Base Blocks": [],
        "Moon Phase": "",
        "Min X": "",
        "Min Y": "",
        "Min Z": "",
        "Max X": "",
        "Max Y": "",
        "Max Z": "",
        "Structures": [],
        "Min Light": "",
        "Max Light": ""
    }
    
    if not special_conditions or not isinstance(special_conditions, str):
        return extracted_info
    
    # Traitement des blocs à proximité (sans "on" avant)
    nearby_blocks = re.findall(r'(?<!on\s)minecraft:[a-z_]+', special_conditions)
    for block in nearby_blocks:
        # Éviter de dupliquer avec les blocs de base
        if f"on {block}" not in special_conditions:
            extracted_info["Needed Nearby Blocks"].append(block)
    
    # Traitement des blocs de base
    base_blocks = re.findall(r'on\s(minecraft:[a-z_]+)', special_conditions)
    extracted_info["Needed Base Blocks"] = base_blocks
    
    # Phase de lune
    moon_phase_match = re.search(r'moonPhase\s*=\s*(\d+)', special_conditions)
    if moon_phase_match:
        extracted_info["Moon Phase"] = moon_phase_match.group(1)
    
    # Coordonnées min/max - Correction du formatage des noms de colonnes
    coord_mapping = {
        "minX": "Min X", 
        "minY": "Min Y", 
        "minZ": "Min Z", 
        "maxX": "Max X", 
        "maxY": "Max Y", 
        "maxZ": "Max Z"
    }
    
    for coord, column_name in coord_mapping.items():
        coord_match = re.search(rf'{coord}\s*=\s*(-?\d+)', special_conditions)
        if coord_match:
            extracted_info[column_name] = coord_match.group(1)
    
    # Structures
    structures = re.findall(r'structure:([a-z_:]+)', special_conditions)
    extracted_info["Structures"] = structures
    
    # Lumière min/max
    min_light_match = re.search(r'minLight\s*=\s*(\d+)', special_conditions)
    if min_light_match:
        extracted_info["Min Light"] = min_light_match.group(1)
    
    max_light_match = re.search(r'maxLight\s*=\s*(\d+)', special_conditions)
    if max_light_match:
        extracted_info["Max Light"] = max_light_match.group(1)
    
    # Convertir les listes en chaînes
    for key in ["Needed Nearby Blocks", "Needed Base Blocks", "Structures"]:
        if extracted_info[key]:
            extracted_info[key] = ", ".join(extracted_info[key])
    
    return extracted_info

# Extrait les données de spawn de Pokémon à partir d'un fichier JSON
def extract_spawn_data(json_file_path, tag_to_biomes, valid_biomes, valid_tags):
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
                dimensions = ", ".join(condition.get("dimensions", []))
                
                # Récupérer la liste des biomes et résoudre les tags
                biomes_list = condition.get("biomes", [])
                biomes_str = ", ".join(biomes_list)
                biomes = resolve_biome_tags_in_string(biomes_str, tag_to_biomes, valid_biomes, valid_tags)
                
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
    parser.add_argument("--biome-tags", default="biomes_tags.txt", help="Chemin vers le fichier de tags de biomes")
    args = parser.parse_args()

    # Charger les tags de biomes
    print(f"Chargement des tags de biomes depuis {args.biome_tags}...")
    tag_to_biomes, valid_biomes, valid_tags = load_biome_tags(args.biome_tags)
    print(f"Chargés {len(tag_to_biomes)} tags de biomes et {len(valid_biomes)} biomes valides.")

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
                    rows = extract_spawn_data(json_file_path, tag_to_biomes, valid_biomes, valid_tags)
                    all_rows.extend(rows)
    
    # Création du DataFrame pandas avec les données extraites
    df_config = pd.DataFrame(all_rows, columns=base_columns)
    
    # Traitement du fichier Excel additionnel si spécifié
    if args.additional:
        try:
            # Lecture du fichier Excel additionnel, y compris la colonne O (conditions spéciales)
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
            
            # Identifier la colonne des conditions spéciales (colonne O)
            special_conditions_col = None
            for col in df_additional.columns:
                if 'condition' in col.lower() or df_additional.columns.get_loc(col) == 14:  # 14 est l'index de la colonne O (0-based)
                    special_conditions_col = col
                    print(f"Colonne des conditions spéciales identifiée : {col}")
                    break
            
            # Sélection des colonnes qui nous intéressent
            cols_to_keep = ["Pokemon"] + [v for k, v in mapping.items() if v != "Pokemon"]
            if special_conditions_col:
                cols_to_keep.append(special_conditions_col)
            df_additional = df_additional[[col for col in cols_to_keep if col in df_additional.columns]]
            
            # Transformation des données additionnelles au format attendu
            additional_rows = []
            for idx, row in df_additional.iterrows():
                new_row = {col: "" for col in base_columns}
                
                # Traiter les colonnes standards
                for col in [c for c in cols_to_keep if c != special_conditions_col]:
                    if col in row and pd.notna(row[col]):
                        value = row[col]
                        # Pour la colonne "Biomes", utiliser la version permissive qui ne filtre pas les biomes inconnus
                        if col == "Biomes" and isinstance(value, str):
                            value = resolve_biome_tags_in_string_lenient(value, tag_to_biomes)
                        new_row[col] = value
                
                # Traiter les conditions spéciales
                if special_conditions_col and pd.notna(row[special_conditions_col]):
                    special_conditions = row[special_conditions_col]
                    parsed_conditions = parse_special_conditions(special_conditions)
                    
                    # Intégrer les conditions extraites dans les données
                    for field, value in parsed_conditions.items():
                        if value:  # Ne pas écraser les champs existants si la valeur est vide
                            # Si le champ existe déjà et n'est pas vide, fusionner les valeurs
                            if new_row[field] and isinstance(value, str) and "," in value:
                                existing_values = set(new_row[field].split(", "))
                                new_values = set(value.split(", "))
                                combined = existing_values.union(new_values)
                                new_row[field] = ", ".join(sorted(combined))
                            else:
                                new_row[field] = value
                
                additional_rows.append(new_row)
            df_additional_transformed = pd.DataFrame(additional_rows, columns=base_columns)
            
            # Concaténation des données extraites et additionnelles
            df_combined = pd.concat([df_config, df_additional_transformed], ignore_index=True)
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier additionnel {args.additional}: {e}")
            df_combined = df_config
    else:
        df_combined = df_config
    
    # DataFrame final avec toutes les colonnes
    df_final = df_combined
    
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
