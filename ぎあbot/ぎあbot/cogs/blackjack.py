import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import random
from utils import process_rank_system  # ランクシステムを読み込み

# --- 設定 ---
LOG_CHANNEL_ID = 1502678682752258049 # バカラと同じログチャンネルに合わせる場合はこちら
EXCLUDE_IDS = [718428067340615730, 719461059248783401]
PROFIT_LIMIT = 50000

def get_card():
    suits = ['♠️', '♥️', '♣️', '♦️']
    vals = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    val = random.choice(vals)
    suit = random.choice(suits)
    points = 10 if val in ['J', 'Q', 'K'] else (11 if val == 'A' else int(val))
    return {"display": f"{suit}{val}", "val": val, "points": points}

def calculate_score(hand):
    score = sum(card['points'] for card in hand)
    ace_count = sum(1 for card in hand if card['val'] == 'A')
    while score > 21 and ace_count > 0:
        score -= 10
        ace_count -= 1
    return score

class BJGameView(ui.View):
    def __init__(self, bot, user, bet, rank_emb=None): # rank_embを受け取れるように
        super().__init__(timeout=120)
        self.bot, self.user, self.bet = bot, user, bet
        self.player_hand = [get_card(), get_card()]
        self.dealer_hand = [get_card(), get_card()]
        self.can_win = True
        self.rank_emb = rank_emb # 現在のランク進捗

    async def check_rigged(self):
        if self.bet >= 1000:
            if random.random() > 0.38: self.can_win = False
        try:
            res = self.bot.supabase.table("user_coins").select("total_profit").eq("user_id", str(self.user.id)).execute()
            if res.data:
                tp = res.data[0].get('total_profit', 0)
                if tp >= PROFIT_LIMIT:
                    if random.random() > 0.38: self.can_win = False
        except: pass

    def create_embed(self, show=False, status="あなたのターン"):
        p_s = calculate_score(self.player_hand)
        d_s = calculate_score(self.dealer_hand) if show else "?"
        emb = discord.Embed(title=f"🃏 BJ - {status}", color=0x2b2d31)
        d_cards = " ".join([f"[`{c['display']}`]" for c in (self.dealer_hand if show else [self.dealer_hand[0], {"display":"❓"}])])
        
        emb.add_field(name=f"🏢 ディーラー [{d_s}]", value=d_cards, inline=False)
        emb.add_field(name=f"👤 あなた [{p_s}]", value=" ".join([f"[`{c['display']}`]" for c in self.player_hand]), inline=False)
        
        # ゲーム中または終了時にランク進捗を表示
        if self.rank_emb:
            emb.add_field(name="🛡️ ランク進捗", value=self.rank_emb.description, inline=False)
            
        emb.set_footer(text=f"BET: {self.bet:,}枚")
        return emb

    @ui.button(label="ヒット", style=discord.ButtonStyle.primary, emoji="👆")
    async def hit(self, i, b):
        self.player_hand.append(get_card())
        if calculate_score(self.player_hand) > 21:
            await self.finish(i, "BUST")
        else:
            await i.response.edit_message(embed=self.create_embed())

    @ui.button(label="スタンド", style=discord.ButtonStyle.success, emoji="✋")
    async def stand(self, i, b):
        while calculate_score(self.dealer_hand) < 17:
            self.dealer_hand.append(get_card())
        
        p_s = calculate_score(self.player_hand)
        d_s = calculate_score(self.dealer_hand)
        
        if not self.can_win and (d_s > 21 or p_s > d_s):
            final_d_score = min(p_s + 1, 21)
        else:
            final_d_score = d_s

        if final_d_score > 21:
            res = "WIN"
        elif p_s > final_d_score:
            res = "WIN"
        elif p_s < final_d_score:
            res = "LOSE"
        else:
            res = "PUSH"

        await self.finish(i, res, override_d_score=final_d_score)

    async def finish(self, i, res, override_d_score=None):
        self.stop()
        payout = int(self.bet * 2) if res == "WIN" else (int(self.bet) if res == "PUSH" else 0)
        
        # 当たった場合のみ払い戻し（消費は開始時にprocess_rank_systemで行済み）
        if payout > 0:
            self.bot.supabase.rpc('update_user_stats', {'u_id': str(self.user.id), 'coin_change': payout}).execute()
        
        await self.send_log(res, payout)

        color = 0xFFD700 if res == "WIN" else 0xFF0000 if res in ["LOSE", "BUST"] else 0xAAAAAA
        p_s = calculate_score(self.player_hand)
        d_s = override_d_score if override_d_score else calculate_score(self.dealer_hand)
        
        msg = "✨ 勝利！" if res=="WIN" else "💀 敗北..." if res=="LOSE" else "💥 バースト！" if res=="BUST" else "⚖️ 引き分け"
        
        # 最終Embed表示
        emb = self.create_embed(show=True, status="ゲーム終了")
        emb.color = color
        emb.description = f"## {msg}\n払い戻し: {payout:,}枚"
        
        await i.response.edit_message(embed=emb, view=None)

    async def send_log(self, res, payout):
        if self.user.id in EXCLUDE_IDS: return
        chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if not chan: return
        
        profit = payout - self.bet
        adj_status = "OFF" if self.can_win else "ON"
        
        log_emb = discord.Embed(title="📝 BJ記録", color=0x2b2d31)
        log_emb.description = (
            f"**ユーザー**　**結果**　**損益**\n"
            f"{self.user.mention}　{res}　{profit:+,}枚\n\n"
            f"調整: {adj_status} ・ 今日 {discord.utils.utcnow().strftime('%H:%M')}"
        )
        await chan.send(embed=log_emb)

# --- パネル部分 ---
class BlackjackNewGia(commands.Cog):
    def __init__(self, bot):
        self.bot, self.user_bets = bot, {}

    @app_commands.command(name="bj", description="ブラックジャックを開始します")
    async def bj(self, interaction: discord.Interaction):
        emb = discord.Embed(
            title="🎰 ぎあカジノ・ブラックジャック",
            description=(
                "ディーラーと対決！「21」に近い方が勝ちです。\n\n"
                "・21を超えると即負け（バースト）\n"
                "・J,Q,Kは「10」、Aは「1または11」として計算\n"
                "・ディーラーは「17」以上になるまで引き続けます\n\n"
                "1. `⌨️金額設定`で賭ける枚数を入力\n"
                "2. `🔥勝負開始！`でゲームを始めます"
            ),
            color=0x00ff00
        )
        await interaction.response.send_message(embed=emb, view=BJMainView(self.bot, self))

class BJMainView(ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot, self.cog = bot, cog

    @ui.button(label="金額設定", style=discord.ButtonStyle.secondary, emoji="⌨️")
    async def set_bet(self, i, b):
        modal = ui.Modal(title="ベット額設定")
        amount_input = ui.TextInput(label="枚数", default="100")
        modal.add_item(amount_input)
        async def on_submit(inter):
            if not amount_input.value.isdigit(): return await inter.response.send_message("数字を入れてね", ephemeral=True)
            self.cog.user_bets[inter.user.id] = int(amount_input.value)
            await inter.response.send_message(f"✅ {int(amount_input.value):,}枚に設定しました。", ephemeral=True)
        modal.on_submit = on_submit
        await i.response.send_modal(modal)

    @ui.button(label="勝負開始！", style=discord.ButtonStyle.danger, emoji="🔥")
    async def start(self, i, b):
        bet = self.cog.user_bets.get(i.user.id, 100)
        
        # 1. 所持コインチェック
        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
        if not res.data or res.data[0]['coin_count'] < bet:
            return await i.response.send_message("❌ コインが足りません", ephemeral=True)
        
        # 2. ランクシステム側でコインを消費 & ランクアップ判定
        # utils.py の process_rank_system を呼び出す
        rank_emb = await process_rank_system(self.bot, i.user.id, bet)
        
        # 3. ゲーム開始
        gv = BJGameView(self.bot, i.user, bet, rank_emb=rank_emb)
        await gv.check_rigged()
        await i.response.send_message(embed=gv.create_embed(), view=gv, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BlackjackNewGia(bot))