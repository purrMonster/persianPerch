"""rollup: the current bodyLanguage of every subject, worst-of: app -> node -> fleet.

Design plan 3.3: a node's state is the worst of its apps (and its own: vitals, whether
Komodo can see it); the fleet's is the worst of its nodes, and of perch's own
collectors, because a watcher that has gone quiet is a problem the fleet has.

Only apps with something to watch count (a compose file, so purr has containers to
look at). An app with nothing to watch stays out of the rollup instead of keeping the
whole fleet at ``unknown`` for ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .bodyLanguage import LEVELS, BodyLanguage, worstOf
from .catTree import App, Fleet
from .scentTrail import ScentTrail, State


@dataclass(frozen=True)
class Attention:
    """One thing that needs a look: an app, a node or a collector at tailFlick or worse."""

    subject: str
    label: str
    level: BodyLanguage
    title: str
    since: datetime
    href: str | None


class Status:
    def __init__(self, fleet: Fleet, trail: ScentTrail) -> None:
        self.fleet = fleet
        self.states = trail.states()

    # -- levels -----------------------------------------------------------------

    @staticmethod
    def watched(app: App) -> bool:
        return bool(app.containers or app.images)

    def _watchedApps(self, nodeName: str) -> list[App]:
        node = self.fleet.node(nodeName)
        return [a for a in (node.apps if node else []) if self.watched(a)]

    def appState(self, node: str, app: str) -> State | None:
        return self.states.get(f"app:{node}/{app}")

    def app(self, node: str, app: str) -> BodyLanguage:
        state = self.appState(node, app)
        return state.bodyLanguage if state else BodyLanguage.unknown

    def nodeState(self, name: str) -> State | None:
        return self.states.get(f"node:{name}")

    def node(self, name: str) -> BodyLanguage:
        levels = [self.app(name, a.name) for a in self._watchedApps(name)]
        own = self.nodeState(name)
        if own:
            levels.append(own.bodyLanguage)
        levels.extend(s.bodyLanguage for s in self.agents(name))
        levels.extend(s.bodyLanguage for s in self.disks(name))
        return worstOf(levels)

    def agents(self, nodeName: str) -> list[State]:
        """What watches the node's backups and answers for its agent: groom's latest night of each job
        (``groom:<node>/<job>``) and kitten's heartbeat (``kitten:<node>``). They count toward the
        node: a backup that didn't run, or an agent that went quiet, is a problem the node has."""
        prefix = f"groom:{nodeName}/"
        mine = [s for s in self.states.values() if s.subject.startswith(prefix)]
        mine.sort(key=lambda s: s.subject)
        beat = self.states.get(f"kitten:{nodeName}")
        return ([beat] if beat else []) + mine

    # -- glare, disks, binocs (M4) ---------------------------------------------------------

    def glare(self) -> list[State]:
        """Gatus's endpoints, as glare last read them: worst first, then by name."""
        found = [s for s in self.states.values() if s.subject.startswith("glare:")]
        return sorted(found, key=lambda s: (-s.bodyLanguage.rank, (s.detail or {}).get("name", s.subject).lower()))

    def tunnel(self) -> State | None:
        """binocs's tunnel is Gatus's own check of it (05 plan C7): the glare state, never a request of its own."""
        from .senses.binocs import TUNNEL_KEY

        return self.states.get(f"glare:{TUNNEL_KEY}")

    def disks(self, nodeName: str | None = None) -> list[State]:
        """Drives Scrutiny reports. With a node: those whose collector host is that node; without: every one."""
        found = [s for s in self.states.values() if s.subject.startswith("disk:")]
        if nodeName is not None:
            found = [s for s in found if (s.detail or {}).get("host", "").lower() == nodeName.lower()]
        return sorted(found, key=lambda s: s.subject)

    def looseDisks(self) -> list[State]:
        """Drives whose host isn't a node of the fleet: they count toward the fleet, not toward a node."""
        names = {n.name.lower() for n in self.fleet.nodes}
        return [s for s in self.disks() if (s.detail or {}).get("host", "").lower() not in names]

    def binocs(self) -> list[State]:
        """Notices only (earTwitch at most): shown on the overview, never part of the fleet's level."""
        return sorted((s for s in self.states.values() if s.subject.startswith("binocs:")), key=lambda s: s.subject)

    def collectors(self) -> dict[str, State]:
        return {s.subject.partition(":")[2]: s for s in self.states.values() if s.subject.startswith("collector:")}

    def fleetLevel(self) -> BodyLanguage:
        levels = [self.node(n.name) for n in self.fleet.nodes]
        levels += [s.bodyLanguage for s in self.collectors().values()]
        levels += [s.bodyLanguage for s in self.glare()]
        levels += [s.bodyLanguage for s in self.looseDisks()]
        return worstOf(levels)

    # -- counts, for the overview ---------------------------------------------------

    def counts(self) -> dict[BodyLanguage, int]:
        counts = {level: 0 for level in (*LEVELS, BodyLanguage.unknown)}
        for node in self.fleet.nodes:
            for app in self._watchedApps(node.name):
                counts[self.app(node.name, app.name)] += 1
        return counts

    def upCount(self, nodeName: str) -> tuple[int, int]:
        """(apps not failing, apps watched): earTwitch is a notice, still up."""
        apps = self._watchedApps(nodeName)
        up = sum(1 for a in apps if self.app(nodeName, a.name) in (BodyLanguage.slowBlink, BodyLanguage.earTwitch))
        return up, len(apps)

    def unknownApps(self, nodeName: str) -> int:
        return sum(1 for a in self._watchedApps(nodeName) if self.app(nodeName, a.name) is BodyLanguage.unknown)

    def attention(self) -> list[Attention]:
        """tailFlick and hiss, worst first, then the longest-standing first."""
        items: list[Attention] = []
        for node in self.fleet.nodes:
            own = self.nodeState(node.name)
            if own and own.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                items.append(self._item(own, node.name, f"/tree/{node.name}"))
            for app in self._watchedApps(node.name):
                state = self.appState(node.name, app.name)
                if state and state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                    items.append(self._item(state, f"{node.name}/{app.name}", f"/tree/{node.name}/{app.name}"))
            for state in self.agents(node.name):
                if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                    items.append(self._item(state, node.name, "/groom" if state.subject.startswith("groom:") else None))
            for state in self.disks(node.name):
                if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                    items.append(self._item(state, self._diskLabel(state), f"/tree/{node.name}"))
        for state in (*self.glare(), *self.looseDisks()):
            if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                label = (state.detail or {}).get("name") or self._diskLabel(state)
                items.append(self._item(state, label, None))
        for _name, state in sorted(self.collectors().items()):
            if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                items.append(self._item(state, "", None))  # its title already names it ("purr is late: ...")
        return sorted(items, key=lambda i: (-i.level.rank, i.since))

    @staticmethod
    def _diskLabel(state: State) -> str:
        detail = state.detail or {}
        return f"{detail.get('device', '')} {detail.get('model', '')}".strip() or state.subject

    @staticmethod
    def _item(state: State, label: str, href: str | None) -> Attention:
        return Attention(state.subject, label, state.bodyLanguage, state.title or "", state.since, href)

    def nodeNote(self, nodeName: str) -> tuple[BodyLanguage, str] | None:
        """The one line a node's card shows when something is off: the node's own trouble, or
        its worst app's; or that it is asleep. None when there is nothing to say."""
        own = self.nodeState(nodeName)
        found: list[tuple[BodyLanguage, str]] = []
        if own and own.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
            found.append((own.bodyLanguage, own.title or ""))
        for app in self._watchedApps(nodeName):
            state = self.appState(nodeName, app.name)
            if state and state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                found.append((state.bodyLanguage, f"{app.name} {state.title or ''}".rstrip()))
        for state in self.agents(nodeName):
            if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                found.append((state.bodyLanguage, state.title or ""))
        for state in self.disks(nodeName):
            if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
                found.append((state.bodyLanguage, f"{self._diskLabel(state)}: {state.title or ''}"))
        if found:
            return max(found, key=lambda item: item[0].rank)  # max keeps the first of equals: the node's own
        if own and (own.detail or {}).get("mode") == "asleep":
            return own.bodyLanguage, own.title or ""
        return None

    # -- what purr saw inside an app or node ------------------------------------------

    def vitals(self, nodeName: str) -> dict | None:
        own = self.nodeState(nodeName)
        return own.detail if own else None

    def containers(self, nodeName: str, app: App) -> list[State]:
        prefix = f"container:{nodeName}/"
        mine = {
            s.subject[len(prefix) :]: s
            for s in self.states.values()
            if s.subject.startswith(prefix) and (s.detail or {}).get("app") == app.name
        }
        order = [n for n in app.containers if n in mine] + sorted(set(mine) - set(app.containers))
        return [mine[n] for n in order]

    def strays(self, nodeName: str) -> list[State]:
        """Containers Komodo sees on a node that no app in node.conf owns: shown, never rolled up."""
        prefix = f"container:{nodeName}/"
        return sorted(
            (s for s in self.states.values() if s.subject.startswith(prefix) and (s.detail or {}).get("stray")),
            key=lambda s: s.subject,
        )
