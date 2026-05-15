import discord
from discord import app_commands, ui
from discord.ext import commands
import random
from itertools import combinations
import datetime
# --- 設定 ---
LOG_CHANNEL_ID = 1502678682752258049
SUITS = ['♠️', '♥️', '♣️', '♦️']
RANK_MAP = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}

def evaluate_hand(cards):
    """7枚から最強の5枚を選び、(ランク, 役名, 比較用数値リスト) を返す"""
    best_hand_score = (-1, "High Card", [])
    
    for combo in combinations(cards, 5):
        sorted_cards = sorted(combo, key=lambda x: x['val'], reverse=True)
        values = [c['val'] for c in sorted_cards]
        suits = [c['suit'] for c in sorted_cards]
        
        is_flush = len(set(suits)) == 1
        # 通常のストレートと A-5 ストレートの判定
        is_straight = all(values[i] - values[i+1] == 1 for i in range(4))
        is_low_straight = (values == [14, 5, 4, 3, 2])
        
        if is_low_straight:
            is_straight = True
            values = [5, 4, 3, 2, 1] # 比較用にAを1として扱う

        counts = {v: values.count(v) for v in set(values)}
        counts_list = sorted(counts.values(), reverse=True)
        unique_values = sorted(counts.keys(), key=lambda x: (counts[x], x), reverse=True)

        if is_straight and is_flush and values[0] == 14:
            score = (10, "Royal Flush", values)
        elif is_straight and is_flush:
            score = (9, "Straight Flush", values)
        elif counts_list == [4, 1]:
            score = (8, "Four of a Kind", unique_values)
        elif counts_list == [3, 2]:
            score = (7, "Full House", unique_values)
        elif is_flush:
            score = (6, "Flush", values)
        elif is_straight:
            score = (5, "Straight", values)
        elif counts_list == [3, 1, 1]:
            score = (4, "Three of a Kind", unique_values)
        elif counts_list == [2, 2, 1]:
            score = (3, "Two Pair", unique_values)
        elif counts_list == [2, 1, 1, 1]:
            score = (2, "One Pair", unique_values)
        else:
            score = (1, "High Card", values)

        if score[0] > best_hand_score[0] or (score[0] == best_hand_score[0] and score[2] > best_hand_score[2]):
            best_hand_score = score
            
    return best_hand_score

class PokerPlayer:
    def __init__(self, user):
        self.user = user
        self.hand = []
        self.is_folded = False
        self.bet_in_phase = 0
        self.total_bet = 0

class PokerActionButton(ui.Button):
    def __init__(self, label, style, action_type):
        super().__init__(label=label, style=style)
        self.action_type = action_type

    async def callback(self, i: discord.Interaction):
        view: 'PokerGameView' = self.view
        player = view.players[view.current_turn_idx]
        
        if i.user.id != player.user.id:
            return await i.response.send_message("君の番じゃないよ！", ephemeral=True)

        if self.action_type == "call":
            diff = view.current_bet - player.bet_in_phase
            view.bot.supabase.rpc('update_user_stats', {'u_id': str(i.user.id), 'coin_change': -diff}).execute()
            player.bet_in_phase += diff
            view.pot += diff
        elif self.action_type == "raise":
            raise_amt = 100
            diff = (view.current_bet + raise_amt) - player.bet_in_phase
            view.bot.supabase.rpc('update_user_stats', {'u_id': str(i.user.id), 'coin_change': -diff}).execute()
            player.bet_in_phase += diff
            view.pot += diff
            view.current_bet = player.bet_in_phase
            view.action_counter = 0 
        elif self.action_type == "fold":
            player.is_folded = True

        view.action_counter += 1
        num_p = len(view.players)
        view.current_turn_idx = (view.current_turn_idx + 1) % num_p
        
        while view.players[view.current_turn_idx].is_folded:
            view.current_turn_idx = (view.current_turn_idx + 1) % num_p

        active = [p for p in view.players if not p.is_folded]
        if len(active) == 1:
            await view.showdown()
        elif view.action_counter >= len(active) and all(p.bet_in_phase == view.current_bet for p in active):
            await view.proceed_phase(i)
        else:
            await i.response.edit_message(embed=view.create_main_embed(), view=view)

class PokerGameView(ui.View):
    def __init__(self, bot, creator, entry_bet):
        super().__init__(timeout=900)
        self.bot, self.creator, self.min_bet = bot, creator, entry_bet
        self.players = [PokerPlayer(creator)]
        self.pot = 0
        self.current_bet = 0
        self.phase = "WAITING"
        self.current_turn_idx = 0
        self.community_cards = []
        self.deck = [{"suit": s, "rank": r, "val": v} for s in SUITS for r, v in RANK_MAP.items()]
        random.shuffle(self.deck)
        self.action_counter = 0
        self.message = None

    def create_main_embed(self):
        emb = discord.Embed(title=f"🃏 本格ポーカー - {self.phase}", color=0x2ecc71)
        cc = " ".join([f"{c['suit']}`{c['rank']}`" for c in self.community_cards]) or "🎴 🎴 🎴 🎴 🎴"
        emb.add_field(name="🏛️ 場", value=f"### {cc}", inline=False)
        p_info = ""
        for i, p in enumerate(self.players):
            mark = "▶️" if i == self.current_turn_idx and self.phase != "WAITING" else "👤"
            p_info += f"{mark} **{p.user.display_name}**: {p.bet_in_phase:,}枚" + (" (FOLD)" if p.is_folded else "") + "\n"
        emb.add_field(name="👥 プレイヤー", value=p_info, inline=True)
        emb.add_field(name="💰 ポット合計", value=f"## {self.pot:,}", inline=True)
        return emb

    @ui.button(label="参加", style=discord.ButtonStyle.primary)
    async def join(self, i, b):
        if any(p.user.id == i.user.id for p in self.players): return await i.response.send_message("既に参加中", ephemeral=True)
        self.players.append(PokerPlayer(i.user))
        await i.response.edit_message(embed=self.create_main_embed())

    @ui.button(label="開始", style=discord.ButtonStyle.danger)
    async def start(self, i, b):
        if i.user.id != self.creator.id: return
        self.phase = "PRE-FLOP"
        for p in self.players:
            p.hand = [self.deck.pop(), self.deck.pop()]
            try:
                h_s = ' '.join([f"{c['suit']}`{c['rank']}`" for c in p.hand])
                await p.user.send(f"【手札】 {h_s}")
            except: pass
        self.clear_items()
        self.add_item(PokerActionButton("コール/チェック", discord.ButtonStyle.success, "call"))
        self.add_item(PokerActionButton("レイズ (+100)", discord.ButtonStyle.primary, "raise"))
        self.add_item(PokerActionButton("フォールド", discord.ButtonStyle.secondary, "fold"))
        await i.response.edit_message(embed=self.create_main_embed(), view=self)

    async def proceed_phase(self, i):
        self.action_counter = 0
        for p in self.players: p.bet_in_phase = 0
        self.current_bet = 0
        if self.phase == "PRE-FLOP":
            self.phase, self.community_cards = "FLOP", [self.deck.pop() for _ in range(3)]
        elif self.phase == "FLOP":
            self.phase = "TURN"; self.community_cards.append(self.deck.pop())
        elif self.phase == "TURN":
            self.phase = "RIVER"; self.community_cards.append(self.deck.pop())
        else:
            await self.showdown(); return
        self.current_turn_idx = 0
        await i.response.edit_message(embed=self.create_main_embed(), view=self)

    async def showdown(self):
        active = [p for p in self.players if not p.is_folded]
        evaluated = []
        for p in active:
            res = evaluate_hand(p.hand + self.community_cards)
            evaluated.append((p, res))

        evaluated.sort(key=lambda x: (x[1][0], x[1][2]), reverse=True)
        winner, win_res = evaluated[0]
        
        self.bot.supabase.rpc('update_user_stats', {'u_id': str(winner.user.id), 'coin_change': self.pot}).execute()
        
        emb = self.create_main_embed()
        emb.title = "🏆 結果発表"
        res_list = [f"**{p.user.display_name}**: {res[1]}" for p, res in evaluated]
        emb.description = f"### 🎉 勝者: {winner.user.mention}\n**役**: {win_res[1]}\n**獲得**: {self.pot:,} 枚\n\n" + "\n".join(res_list)
        
        await self.message.edit(embed=emb, view=None)

class PokerSystem(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="poker", description="本格ポーカー")
    async def poker(self, interaction: discord.Interaction, bet: int = 100):
        view = PokerGameView(self.bot, interaction.user, bet)
        await interaction.response.send_message(embed=view.create_main_embed(), view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(PokerSystem(bot))