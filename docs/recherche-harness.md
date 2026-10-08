# Recherche : harness pour l’alpha StoneBench

Recherche documentaire effectuée le 8 octobre 2026, puis complétée sur la remise de checkpoint à l’approche du budget. **Q24 est confirmée :** Inspect AI est le harness de référence de l’alpha et les outils StoneBench sont fournis en MCP. Cette note précise ce choix et les limites à valider dans un prototype.

## Architecture retenue pour Q24

StoneBench utilisera **Inspect AI comme premier harness de référence**, avec les outils du domaine exposés par un serveur **MCP**. StoneBench gardera le contrôle du serveur Minecraft, la remise à zéro des mondes et la vérification déterministe ; Inspect fournira l’agent et le cadre d’évaluation. Cela évite de développer dans StoneBench une boucle d’appels aux modèles.

Inspect se connecte à des serveurs MCP locaux par `stdio` ou à un endpoint HTTP, et peut rendre tous les outils du serveur disponibles à son agent ou en sélectionner un sous-ensemble. Un même serveur MCP StoneBench pourrait donc aussi être connecté à un autre harness compatible. [MCP dans Inspect](https://inspect.aisi.org.uk/tools-mcp.html)

Pour établir le premier résultat comparable, je partirais de l’agent ReAct fourni par Inspect, avec un prompt, une liste d’outils et un budget de tokens identiques pour chaque modèle. Inspect fournit un grand choix de fournisseurs hébergés et locaux, et peut aussi se connecter à une API compatible avec OpenAI. Il prend en charge les limites de tokens au niveau d’un échantillon et conserve les journaux d’exécution, les transcriptions et les statistiques d’utilisation du modèle. [Agents Inspect](https://inspect.aisi.org.uk/agents.html), [fournisseurs](https://inspect.aisi.org.uk/providers.html), [limites d’agents](https://inspect.aisi.org.uk/agent-custom.html), [journaux d’évaluation](https://inspect.aisi.org.uk/eval-logs.html)

La conformité, le volume et la vitesse resteraient des résultats séparés : le vérificateur StoneBench calculerait la conformité à partir de l’état du serveur ; des scorers Inspect pourraient rapporter les mesures déterministes de conformité, volume et durée des transitions sans les fondre en un score unique. [Scorers Inspect](https://inspect.aisi.org.uk/scorers.html)

## Soumettre un checkpoint avant la limite de tokens (Q34)

ReAct fournit déjà un outil `submit()` pour terminer un essai. Inspect permet de personnaliser cet outil et offre un callback `on_continue` appelé à chaque itération, qui peut transmettre au modèle une demande de soumission. Il n’existe pas de réglage ReAct documenté qui réserve automatiquement un dernier tour ou transforme la limite de tokens en demande de soumission. La limite de tokens au niveau de l’échantillon reste un arrêt de secours ; si elle est atteinte, elle ne garantit pas que le modèle aura pu soumettre son checkpoint. [ReAct et submit](https://inspect.aisi.org.uk/react-agent.html)

La mesure cumulative existe sur `TaskState.token_usage`, et c’est le même compteur que celui de la limite d’échantillon. Le callback ReAct reçoit toutefois un `AgentState` (historique et dernière réponse), pas le `TaskState`. Le minimum crédible est donc un petit adaptateur d’agent qui transmet au callback le compteur de l’échantillon. Au seuil souple, le callback demande à l’agent d’entrer dans une phase lecture, vérification et soumission uniquement ; une garde partagée refuse alors les outils qui modifient la construction. L’agent choisit et soumet l’identifiant du checkpoint qu’il juge meilleur, avec son statut terminé ou incomplet. Le `submit()` personnalisé transmet ce choix au scoreur, sans remplacer la décision par une sauvegarde automatique de l’état courant. Cela conserve la boucle de génération ReAct d’Inspect, sans la réécrire. Il faut vérifier cette liaison avec la version Inspect épinglée avant de la considérer comme acquise. [État de tâche et compteur](https://inspect.aisi.org.uk/reference/inspect_ai.solver.html), [callback ReAct](https://inspect.aisi.org.uk/reference/inspect_ai.agent.html)

Le budget total `B` doit inclure cette soumission finale. Comme chaque tour renvoie l’historique au modèle, le dernier tour ajoute de nouveau les tokens de son prompt complet, puis ses tokens de sortie, y compris le raisonnement comptabilisé par Inspect. Une réserve `R` doit couvrir l’instruction de finalisation, le prompt complet estimé du tour de soumission, la taille de sortie maximale configurée et une marge. **5 à 10 % de `B` peut servir de valeur initiale configurable à calibrer**, mais ne garantit pas à lui seul qu’un long historique tiendra dans la réserve. Le seuil souple est `B − R`; la limite d’échantillon reste `B`. [Comptage des tokens](https://inspect.aisi.org.uk/reference/inspect_ai.util.html)

La limite Inspect est réactive : l’usage d’un appel est connu à partir de la réponse du fournisseur. Un appel déjà lancé peut donc terminer avec une consommation qui dépasse le seuil, voire le plafond annoncé. Pour réduire cet écart, borner les sorties par appel et faire déclencher la demande de soumission avec assez de marge pour un tour complet ; consigner tout dépassement comme tel. Cette garantie de non-dépassement n’est pas établie par la documentation Inspect seule. C’est une limite pratique du comptage après génération, à valider sur les fournisseurs retenus.

## Limites à garder explicites

- Le budget Inspect est un budget de tokens. Les plafonds de 6 000 ticks par avancement et de 36 000 ticks par transition sont des limites de jeu : le contrôleur Minecraft doit les appliquer lui-même et retourner un résultat clair si une limite est atteinte. Une limite de temps Inspect mesure du temps réel, pas des ticks.
- Inspect mesure un modèle dans le cadre de l’agent, du prompt et des outils fournis. Le ReAct d’Inspect crée donc une condition de référence reproductible ; comparer des agents issus de harnesses différents mesurera aussi leurs différences d’orchestration. Il faudra inscrire ces paramètres avec chaque résultat.
- Une instance Minecraft représente un état mutable. Pour la première alpha, les essais doivent être séquencés ou disposer de mondes/instances isolés avant d’activer l’exécution parallèle.
- Inspect MCP peut appeler un serveur HTTP distant au nom du fournisseur dans certains cas. Pour conserver le contrôle des appels d’outils et des résultats dans le journal et les limites de l’évaluation, garder l’exécution MCP locale au processus Inspect, même si le contrôleur Minecraft est un service séparé sur la machine.

Codex Desktop et Codex CLI savent également se connecter à des outils MCP ; c’est une option pratique pour essayer les outils avec un agent interactif pendant le développement. Pour le harness de référence, Inspect est mieux adapté à la comparaison entre plusieurs modèles, car il apporte déjà la sélection de fournisseurs, les limites par échantillon et les journaux d’évaluation. [MCP dans Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

## Sources primaires

- [Inspect — Model Context Protocol](https://inspect.aisi.org.uk/tools-mcp.html)
- [Inspect — Using Agents](https://inspect.aisi.org.uk/agents.html)
- [Inspect — Model Providers](https://inspect.aisi.org.uk/providers.html)
- [Inspect — Custom Agents and Limits](https://inspect.aisi.org.uk/agent-custom.html)
- [Inspect — Log Files](https://inspect.aisi.org.uk/eval-logs.html)
- [Inspect — Scorers](https://inspect.aisi.org.uk/scorers.html)
- [Inspect — ReAct Agent](https://inspect.aisi.org.uk/react-agent.html)
- [Inspect — Agent API](https://inspect.aisi.org.uk/reference/inspect_ai.agent.html)
- [Inspect — TaskState](https://inspect.aisi.org.uk/reference/inspect_ai.solver.html)
- [Inspect — Token Limits](https://inspect.aisi.org.uk/reference/inspect_ai.util.html)
- [OpenAI — MCP in Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
