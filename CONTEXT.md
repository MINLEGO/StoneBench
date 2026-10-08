# StoneBench

StoneBench évalue la capacité de modèles à construire des portes redstone dans Minecraft, avec des outils permettant de tester et de corriger leurs constructions.

## Langage

**Construction** :
Ensemble de blocs, avec leurs états et données internes, proposé par un agent pour réaliser la porte demandée à partir d'une zone initialement vide. Les constructions utilisant des entités sont exclues de l'alpha.

**Porte regular** :
Agencement par défaut des blocs d'une porte à pistons dans le référentiel communautaire choisi. C'est la catégorie retenue pour l'alpha, sans motif ni restriction spécifique.
_Éviter_ : Porte logique.

**Cadre (frame)** :
Section du passage contenant les blocs de la porte lorsqu'elle est fermée.

**Encadrement physique** :
Blocs construits autour du passage par l'agent. Il est distinct du cadre géométrique qui désigne la section occupée par les blocs de porte fermée ; ses exclusions de volume suivent le référentiel.

**Taille de porte** :
Dimensions minimales décrivant le type de porte à l'intérieur du cadre. Elle est distincte des dimensions de l'ensemble de la construction.

**État stable** :
État dans lequel la construction reste, ou auquel elle revient périodiquement sans fin, jusqu'à recevoir un signal d'entrée, selon le référentiel. La stabilité n'impose donc pas nécessairement l'immobilité de tous les composants.

**Conformité** :
Correspondance d'une construction aux critères précis de la porte demandée, selon le référentiel choisi. Elle est distincte d'un record ou d'une amélioration par rapport aux constructions connues.

**Conformité au protocole alpha** :
Satisfaction des critères regular DOOR et du protocole fonctionnel retenus par StoneBench pour l'alpha. Elle ne certifie pas toutes les conditions communautaires d'admissibilité aux records.

**Règle non vérifiée** :
Règle du référentiel dont la satisfaction n'est pas évaluée dans le périmètre courant. Ce statut ne signifie ni réussite ni échec.

**Volume** :
Produit des dimensions de l'enveloppe du circuit, cumulées au cours des états et des opérations, avec les exclusions du référentiel. C'est une mesure d'encombrement, distincte du nombre de blocs placés et de la taille de la porte.

**Temps d'ouverture** :
Temps entre l'interaction d'entrée et la fin du dernier mouvement permettant au passage d'atteindre la disposition ouverte requise par le type de porte. Il se mesure en ticks du jeu.

**Temps de fermeture** :
Temps entre l'interaction d'entrée et le dernier mouvement des blocs de porte pendant la fermeture. Il se mesure en ticks du jeu.

**Vérification de conformité** :
Évaluation d'une construction qui indique les critères satisfaits et non satisfaits. Ses résultats sont accessibles à l'agent pendant la construction.

**Checkpoint de construction** :
Copie sauvegardée d'une construction dans un état stable.

**Cycle de porte** :
Une ouverture et une fermeture complètes de la porte par son dispositif d'entrée.

**Retour à l'état initial** :
Récurrence de l'état de référence des blocs, inventaires et données internes après des cycles complets de la porte.

**Fin de transition alpha** :
État dans lequel plus rien ne change dans la construction et aucun événement programmé ne reste en attente. C'est le point attendu avant la commande suivante du protocole alpha, distinct de la stabilité périodique admise dans le référentiel communautaire.

**État initial (état 0)** :
État de référence de la construction avant les cycles d'essai. Les essais d'entrée directe et par répéteur partent de ce même état.

**Réglage d'un composant** :
Paramètre configurable lors de la construction ou par une interaction normale en jeu, tel que l'orientation, le délai d'un répéteur ou le mode d'un comparateur. Il est distinct des états internes calculés pendant le fonctionnement.

**Soumission finale** :
Checkpoint désigné par l'agent comme sa meilleure construction pour l'objectif demandé, qu'elle soit achevée ou non, puis évalué par le vérificateur.

**Finalisation de tentative** :
Phase précédant l'épuisement du budget dans laquelle l'agent consulte et vérifie ses constructions, puis désigne sa soumission finale sans poursuivre la construction.

**Aucune soumission** :
Issue d'une tentative dans laquelle l'agent n'a désigné aucun checkpoint final. Elle est distincte de la soumission d'une construction non conforme.
