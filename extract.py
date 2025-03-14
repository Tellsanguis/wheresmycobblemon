#!/usr/bin/env python3
import os
import json
import pandas as pd
import argparse
from openpyxl.styles import Alignment
import re
from collections import defaultdict

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
    valid_biomes = set()  # Ensemble pour stocker tous les biomes valides (Registry names)
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
                    
                    # Ajouter le biome à l'ensemble des biomes valides (seulement s'il a un nom)
                    if registry_name:
                        valid_biomes.add(registry_name)
                    
                    # Si des tags sont présents et le registry_name est valide
                    if tags_text and registry_name:
                        # Diviser les tags et les nettoyer
                        tags = [tag.strip() for tag in tags_text.split(',')]
                        
                        # Pour chaque tag, ajouter ce biome à la liste correspondante
                        for tag in tags:
                            if tag:  # Ignorer les tags vides
                                valid_tags.add(tag)
                                # Ajouter aussi la version avec/sans # du tag
                                if tag.startswith('#'):
                                    valid_tags.add(tag[1:])
                                else:
                                    valid_tags.add('#' + tag)
                                
                                # Normaliser le tag (sans le #)
                                normalized_tag = tag.lstrip('#')
                                
                                # Ajouter le tag avec et sans # comme clés
                                if normalized_tag not in tag_to_biomes:
                                    tag_to_biomes[normalized_tag] = []
                                if tag not in tag_to_biomes:
                                    tag_to_biomes[tag] = []
                                
                                tag_to_biomes[normalized_tag].append(registry_name)
                                tag_to_biomes[tag].append(registry_name)
        
        print(f"Biomes valides chargés: {len(valid_biomes)}")
        print(f"Tags valides chargés: {len(valid_tags)}")
        print(f"Associations tag-biomes chargées: {len(tag_to_biomes)}")
        
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
    
    # Chercher une correspondance directe dans notre dictionnaire de tags
    if tag in tag_to_biomes:
        return tag_to_biomes[tag]
    if normalized_tag in tag_to_biomes:
        return tag_to_biomes[normalized_tag]
    
    # Si aucune correspondance directe, vérifier si c'est un tag minecraft:is_ ou cobblemon:is_
    if "cobblemon:is_" in normalized_tag:
        alternate_tag = normalized_tag.replace("cobblemon:is_", "minecraft:is_")
        if alternate_tag in tag_to_biomes:
            return tag_to_biomes[alternate_tag]
        if '#' + alternate_tag in tag_to_biomes:
            return tag_to_biomes['#' + alternate_tag]
    
    # Aucune correspondance trouvée
    return []

# Fonction pour résoudre tous les tags de biomes dans une chaîne (avec validation stricte)
def resolve_biome_tags_in_string(biomes_str, tag_to_biomes, valid_biomes, valid_tags):
    if not biomes_str:
        return ""
    
    # Diviser la chaîne en biomes individuels
    biomes = [b.strip() for b in biomes_str.split(',')]
    all_resolved_biomes = []
    
    for biome in biomes:
        biome = biome.strip()
        if not biome:
            continue
            
        # Si c'est un tag (commence par # ou contient "is_")
        if biome.startswith('#') or ":is_" in biome:
            # S'assurer que le biome a le préfixe # si c'est un tag
            tag = biome if biome.startswith('#') else '#' + biome
            normalized_tag = tag.lstrip('#')
            
            # Vérifier si c'est un tag valide
            if tag in valid_tags or normalized_tag in valid_tags:
                # Essayer de résoudre le tag
                resolved = resolve_biome_tag(tag, tag_to_biomes)
                if resolved:
                    # Ajouter seulement les biomes résolus qui sont valides
                    all_resolved_biomes.extend([b for b in resolved if b in valid_biomes])
            elif "cobblemon:is_" in biome:
                # Essayer avec minecraft:is_ si c'est un tag cobblemon
                minecraft_tag = biome.replace("cobblemon:is_", "minecraft:is_")
                if minecraft_tag in valid_tags or minecraft_tag.lstrip('#') in valid_tags:
                    resolved_minecraft = resolve_biome_tag(minecraft_tag, tag_to_biomes)
                    if resolved_minecraft:
                        all_resolved_biomes.extend([b for b in resolved_minecraft if b in valid_biomes])
        else:
            # C'est un biome direct, vérifier s'il est valide
            if biome in valid_biomes:
                all_resolved_biomes.append(biome)
    
    # Éliminer les doublons et joindre les biomes en une chaîne avec | comme séparateur
    return ' | '.join(sorted(set(all_resolved_biomes)))

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
                dimensions = " | ".join(condition.get("dimensions", []))
                
                # Récupérer la liste des biomes et résoudre les tags
                biomes_list = condition.get("biomes", [])
                biomes_str = ", ".join(biomes_list)
                biomes = resolve_biome_tags_in_string(biomes_str, tag_to_biomes, valid_biomes, valid_tags)
                
                structures = " | ".join(condition.get("structures", []))
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
                labels = " | ".join(condition.get("labels", []))
                label_mode = condition.get("labelMode", "")
                
                # Dimensions physiques
                min_width = condition.get("minWidth", "")
                max_width = condition.get("maxWidth", "")
                min_height = condition.get("minHeight", "")
                max_height = condition.get("maxHeight", "")
                
                # Blocs environnants nécessaires
                needed_nearby_blocks = " | ".join(condition.get("neededNearbyBlocks", []))
                needed_base_blocks = " | ".join(condition.get("neededBaseBlocks", []))
                
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
                stone_requirements_str = " | ".join(stone_requirements)
                
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
                    custom_team = " | ".join(formatted_team)
                
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

# Fonction modifiée pour déterminer les meilleurs biomes de spawn pour chaque entrée de Pokémon
def determine_best_spawn_biomes(df):
    # Fonction auxiliaire pour diviser correctement une chaîne de biomes
    def split_biomes(biomes_str):
        if not biomes_str or not isinstance(biomes_str, str):
            return set()
        # Diviser la chaîne en biomes individuels en tenant compte des séparateurs
        return set(b.strip() for b in biomes_str.split('|') if b.strip())
    
    # Ajouter un identifiant unique pour chaque entrée
    df['entry_id'] = range(len(df))
    
    # Créer un dictionnaire pour stocker les Pokémon par bucket
    pokemon_by_bucket = defaultdict(list)
    for idx, row in df.iterrows():
        if row["Bucket"] and row["Pokemon"]:
            # Créer un identifiant unique pour cette entrée de Pokémon
            unique_id = f"{row['Pokemon']}_{idx}"
            
            pokemon_info = {
                "pokemon": row["Pokemon"],
                "unique_id": unique_id,  # Ajouter l'ID unique
                "biomes": split_biomes(row["Biomes"]),
                "key_item": row["Key Item"],
                "needed_nearby_blocks": split_biomes(row["Needed Nearby Blocks"]),
                "needed_base_blocks": split_biomes(row["Needed Base Blocks"]),
                "stone_requirements": row["Stone Requirements"],
                "custom_pokemons_in_team": row["Custom Pokemons In Team"],
                "entry_id": idx  # Garder l'ID d'entrée original
            }
            pokemon_by_bucket[row["Bucket"]].append(pokemon_info)
    
    # Dictionnaire pour stocker les biomes et le nombre de concurrents pour chaque entrée de Pokémon
    pokemon_biome_competitors = defaultdict(lambda: defaultdict(int))
    
    # Pour chaque bucket, calculer les concurrents par biome pour chaque entrée de Pokémon
    for bucket, pokemon_list in pokemon_by_bucket.items():
        for pokemon_info in pokemon_list:
            unique_id = pokemon_info["unique_id"]
            pokemon_biomes = pokemon_info["biomes"]
            
            # Si le Pokémon n'a pas de biomes spécifiés, passer au suivant
            if not pokemon_biomes:
                continue
            
            # Pour chaque biome de ce Pokémon, trouver les concurrents
            for biome in pokemon_biomes:
                if not biome:  # Ignorer les biomes vides
                    continue
                
                # Ensemble pour stocker les noms uniques des concurrents dans ce biome
                unique_competitors = set()
                
                # Vérifier chaque autre Pokémon dans le bucket
                for other_pokemon in pokemon_list:
                    # Ne pas compter l'entrée elle-même
                    if other_pokemon["unique_id"] != unique_id:
                        # Vérifier si l'autre Pokémon peut apparaître dans ce biome
                        if biome in other_pokemon["biomes"]:
                            # Vérifier les conditions supplémentaires
                            
                            # Condition 1: Key Item
                            key_item_compatible = (
                                not pokemon_info["key_item"] or
                                not other_pokemon["key_item"] or
                                pokemon_info["key_item"] == other_pokemon["key_item"]
                            )
                            
                            # Condition 2: Needed Nearby Blocks
                            nearby_blocks_compatible = (
                                not pokemon_info["needed_nearby_blocks"] or
                                not other_pokemon["needed_nearby_blocks"] or
                                pokemon_info["needed_nearby_blocks"] == other_pokemon["needed_nearby_blocks"]
                            )
                            
                            # Condition 3: Needed Base Blocks
                            base_blocks_compatible = (
                                not pokemon_info["needed_base_blocks"] or
                                not other_pokemon["needed_base_blocks"] or
                                pokemon_info["needed_base_blocks"] == other_pokemon["needed_base_blocks"]
                            )
                            
                            # Condition 4: Stone Requirements
                            stone_requirements_compatible = (
                                not pokemon_info["stone_requirements"] or
                                not other_pokemon["stone_requirements"] or
                                pokemon_info["stone_requirements"] == other_pokemon["stone_requirements"]
                            )
                            
                            # Condition 5: Custom Pokemons In Team
                            custom_team_compatible = (
                                not pokemon_info["custom_pokemons_in_team"] or
                                not other_pokemon["custom_pokemons_in_team"] or
                                pokemon_info["custom_pokemons_in_team"] == other_pokemon["custom_pokemons_in_team"]
                            )
                            
                            # Si toutes les conditions sont compatibles, ajouter comme concurrent
                            if (key_item_compatible and nearby_blocks_compatible and 
                                base_blocks_compatible and stone_requirements_compatible and 
                                custom_team_compatible):
                                
                                # Ajouter le nom du Pokémon à l'ensemble des concurrents uniques
                                unique_competitors.add(other_pokemon["pokemon"])
                
                # Stocker le nombre de concurrents uniques pour cette entrée de Pokémon dans ce biome
                pokemon_biome_competitors[unique_id][biome] = len(unique_competitors)
    
    # Déterminer les meilleurs biomes pour chaque entrée de Pokémon (ceux avec le moins de concurrents)
    best_spawn_biomes = {}
    competitor_counts = {}
    entry_id_to_unique_id = {}
    
    # Créer un mappage de entry_id vers unique_id
    for bucket_pokemons in pokemon_by_bucket.values():
        for pokemon_info in bucket_pokemons:
            entry_id_to_unique_id[pokemon_info["entry_id"]] = pokemon_info["unique_id"]
    
    for unique_id, biome_competitors in pokemon_biome_competitors.items():
        if not biome_competitors:  # Si aucun biome concurrent, passer au suivant
            best_spawn_biomes[unique_id] = ""
            competitor_counts[unique_id] = 0
            continue
        
        # Trouver le nombre minimum de concurrents
        min_competitors = min(biome_competitors.values()) if biome_competitors.values() else 0
        
        # Stocker le nombre de concurrents pour cette entrée de Pokémon
        competitor_counts[unique_id] = min_competitors
        
        # Sélectionner tous les biomes ayant ce nombre minimum de concurrents
        best_biomes = [biome for biome, count in biome_competitors.items() if count == min_competitors]
        
        # Trier les biomes pour une sortie cohérente
        best_biomes.sort()
        
        # Stocker les meilleurs biomes pour cette entrée de Pokémon avec le séparateur
        best_spawn_biomes[unique_id] = " | ".join(best_biomes)
    
    return best_spawn_biomes, competitor_counts, entry_id_to_unique_id

def main():
    # Configuration du parseur d'arguments pour les options en ligne de commande
    parser = argparse.ArgumentParser(
        description="Extrait les données de spawn depuis les fichiers JSON dans 'spawn_pool_world'"
    )
    parser.add_argument("target_dir", help="Dossier cible où chercher les fichiers JSON")
    parser.add_argument("--output", default="spawn_data.xlsx", help="Nom du fichier Excel de sortie")
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
        "Fluid Is Source", "Fluid Block", "Key Item", "Stone Requirements", "Custom Pokemons In Team",
        "Meilleurs biomes de spawn", "Nombre de concurrents"  # Ajout de la colonne nombre de concurrents
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
    df_partial = pd.DataFrame(all_rows)
    
    # S'assurer que les colonnes nécessaires existent
    for col in base_columns:
        if col not in df_partial.columns and col not in ["Meilleurs biomes de spawn", "Nombre de concurrents"]:
            df_partial[col] = ""
    
    # Déterminer les meilleurs biomes de spawn pour chaque entrée de Pokémon
    best_spawn_biomes, competitor_counts, entry_id_to_unique_id = determine_best_spawn_biomes(df_partial)
    
    # Ajouter les colonnes pour les meilleurs biomes et le nombre de concurrents
    df_partial["Meilleurs biomes de spawn"] = ""
    df_partial["Nombre de concurrents"] = ""
    
    # Remplir les colonnes pour chaque entrée
    for idx, row in df_partial.iterrows():
        unique_id = entry_id_to_unique_id.get(idx)
        if unique_id:
            df_partial.at[idx, "Meilleurs biomes de spawn"] = best_spawn_biomes.get(unique_id, "")
            df_partial.at[idx, "Nombre de concurrents"] = competitor_counts.get(unique_id, "")
    
    # S'assurer que toutes les colonnes requises sont présentes
    for col in base_columns:
        if col not in df_partial.columns:
            df_partial[col] = ""
    
    # Créer le DataFrame final avec les colonnes dans l'ordre souhaité
    df_final = df_partial[base_columns]
    
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
