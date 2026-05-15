import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime
import asyncio
import random
from utils import process_rank_system

# --- 設定 ---
LOG_CHANNEL_ID = 1502653911511597076
EXCLUDE_IDS = [718428067340615730, 719461059248783401]
PROFIT_LIMIT = 50000 
NUM_EMOJI = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

def get_card():
    vals = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    suits = ['♠️', '♥️', '♣️', '♦️']
    val = random.choice(vals)
    suit = random.choice(suits)
    if val in ['10', 'J', 'Q', 'K']: points = 0
    elif val == 'A': points = 1
    else: points = int(val)
    return {"display": f"{suit}{val}", "points": points}

def calculate_baccarat_score(hand_visible):
    return sum(card['points'] for card in hand_visible) % 10

class BaccaratGameLogic:
    def __init__(self, bot, user, bet, choice):
        self.bot, self.user, self.bet, self.choice = bot, user, bet, choice
        self.can_win = True

    async def check_rigged(self):
        if self.bet >= 1000:
            if random.random() > 0.38: self.can_win = False
        try:
            res = self.bot.supabase.table("user_coins").select("total_profit").eq("user_id", str(self.user.id)).execute()
            if res.data and res.data[0].get('total_profit', 0) >= PROFIT_LIMIT:
                if random.random() > 0.38: self.can_win = False
        except: pass

    async def play(self, interaction):
        p_full_hand = [get_card(), get_card()]
        b_full_hand = [get_card(), get_card()]
        
        if not self.can_win:
            p_s = (p_full_hand[0]['points'] + p_full_hand[1]['points']) % 10
            b_s = (b_full_hand[0]['points'] + b_full_hand[1]['points']) % 10
            real_winner = "PLAYER" if p_s > b_s else ("BANKER" if b_s > p_s else "TIE")
            if self.choice == real_winner:
                p_full_hand = [{"display": "♣️2", "points": 2}, {"display": "♦️3", "points": 3}]
                b_full_hand = [{"display": "♥️4", "points": 4}, {"display": "♠️5", "points": 5}]

        p_display = ["🎴", "🎴"]
        b_display = ["🎴", "🎴"]

        async def make_embed(status="勝負中...", color=0x2b2d31, rank_embed=None):
            p_visible = [p_full_hand[i] for i, d in enumerate(p_display) if d != "🎴"]
            b_visible = [b_full_hand[i] for i, d in enumerate(b_display) if d != "🎴"]
            p_score = calculate_baccarat_score(p_visible)
            b_score = calculate_baccarat_score(b_visible)
            
            emb = discord.Embed(title=f"🎰 バカラ勝負中...", color=color)
            p_str = " ".join([f"[`{d}`]" if d != "🎴" else "🎴" for d in p_display])
            b_str = " ".join([f"[`{d}`]" if d != "🎴" else "🎴" for d in b_display])
            
            emb.add_field(name=f"🔵 PLAYER [{'❓' if '🎴' in p_display else NUM_EMOJI[p_score]}]", value=p_str, inline=False)
            emb.add_field(name=f"🔴 BANKER [{'❓' if '🎴' in b_display else NUM_EMOJI[b_score]}]", value=b_str, inline=False)
            
            if rank_embed:
                emb.add_field(name="🛡️ ランク進捗", value=rank_embed.description, inline=False)
                
            emb.set_footer(text=f"BET: {self.bet:,} | 予想: {self.choice}")
            return emb

        await interaction.response.send_message(embed=await make_embed(), ephemeral=True)

        for i in range(2):
            await asyncio.sleep(0.8)
            p_display[i] = p_full_hand[i]['display']
            await interaction.edit_original_response(embed=await make_embed())
            await asyncio.sleep(0.8)
            b_display[i] = b_full_hand[i]['display']
            await interaction.edit_original_response(embed=await make_embed())

        p_score = calculate_baccarat_score(p_full_hand)
        b_score = calculate_baccarat_score(b_full_hand)
        
        if p_score <= 5 or b_score <= 5:
            await asyncio.sleep(1.0)
            if p_score <= 5:
                card = get_card()
                p_full_hand.append(card); p_display.append("🎴")
                await interaction.edit_original_response(embed=await make_embed())
                await asyncio.sleep(1.0)
                p_display[2] = card['display']
            if b_score <= 5:
                card = get_card()
                b_full_hand.append(card); b_display.append("🎴")
                await interaction.edit_original_response(embed=await make_embed())
                await asyncio.sleep(1.0)
                b_display[-1] = card['display']
            await interaction.edit_original_response(embed=await make_embed())

        p_fin = calculate_baccarat_score(p_full_hand)
        b_fin = calculate_baccarat_score(b_full_hand)
        winner = "PLAYER" if p_fin > b_fin else ("BANKER" if b_fin > p_fin else "TIE")
        is_win = (self.choice == winner)
        
        win_table = {"PLAYER": 2.0, "BANKER": 1.95, "TIE": 9.0}
        payout = int(self.bet * win_table[self.choice]) if is_win else 0

        # --- ランクシステム連動 ---
        rank_emb = await process_rank_system(self.bot, self.user.id, self.bet)
        
        if is_win:
            self.bot.supabase.rpc('update_user_stats', {'u_id': str(self.user.id), 'coin_change': payout}).execute()

        res_color = 0x00ff00 if is_win else 0xff0000
        final_emb = await make_embed("終了", res_color, rank_embed=rank_emb)
        res_msg = f"## {'✨ 的中！' if is_win else '💀 残念...'}\n勝者: **{winner}**\n払い戻し: {payout:,}枚"
        final_emb.description = res_msg
        await interaction.edit_original_response(embed=final_emb)
        await self.send_log(winner, payout)

    async def send_log(self, winner, payout):
        if self.user.id in EXCLUDE_IDS: return
        chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if chan:
            profit = payout - self.bet
            await chan.send(f"📝 **バカラログ**: {self.user.mention} | 予想:{self.choice} | 結果:{winner} | 損益:{profit:+,}")

# --- パネル部分 (永続化) ---
class BaccaratMainView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_bets = {}

    async def start_game(self, i, choice):
        bet = self.user_bets.get(i.user.id, 100)
        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
        if not res.data or res.data[0]['coin_count'] < bet:
            return await i.response.send_message("❌ コイン不足", ephemeral=True)
        
        game = BaccaratGameLogic(self.bot, i.user, bet, choice)
        await game.check_rigged()
        await game.play(i)

    @ui.button(label="金額設定", style=discord.ButtonStyle.secondary, emoji="⌨️", custom_id="bac_set_bet")
    async def set_bet(self, i, b):
        modal = ui.Modal(title="ベット額")
        amt = ui.TextInput(label="枚数", default="100")
        modal.add_item(amt)
        async def cb(it):
            self.user_bets[it.user.id] = int(amt.value)
            await it.response.send_message(f"✅ {amt.value}枚に設定", ephemeral=True)
        modal.on_submit = cb
        await i.response.send_modal(modal)

    @ui.button(label="PLAYER", style=discord.ButtonStyle.primary, custom_id="bac_player")
    async def p(self, i, b): await self.start_game(i, "PLAYER")
    
    @ui.button(label="BANKER", style=discord.ButtonStyle.danger, custom_id="bac_banker")
    async def b(self, i, b): await self.start_game(i, "BANKER")
    
    @ui.button(label="TIE", style=discord.ButtonStyle.success, custom_id="bac_tie")
    async def t(self, i, b): await self.start_game(i, "TIE")

class Baccarat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="baccarat", description="バカラパネルを表示")
    async def baccarat(self, i: discord.Interaction):
        emb = discord.Embed(title="🎰 ぎあカジノ・バカラ", description="PLAYERかBANKERかTIEを予想してください。", color=0x0000ff)
        await i.response.send_message(embed=emb, view=BaccaratMainView(self.bot))

async def setup(bot):
    await bot.add_cog(Baccarat(bot))