import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import random
from utils import process_rank_system
import datetime

# --- 設定 ---
LOG_CHANNEL_ID = 1502678682752258049
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

# --- ゲーム進行中View ---
class BJGameView(ui.View):
    def __init__(self, bot, user, bet, rank_emb=None):
        super().__init__(timeout=120)
        self.bot, self.user, self.bet = bot, user, bet
        self.player_hand = [get_card(), get_card()]
        self.dealer_hand = [get_card(), get_card()]
        self.can_win = True
        self.rank_emb = rank_emb

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
        self.clear_items()
        await i.response.edit_message(embed=self.create_embed(show=False, status="ディーラーの思考中..."), view=None)
        
        await asyncio.sleep(1.2)
        await i.edit_original_response(embed=self.create_embed(show=True, status="ディーラーのターン..."))

        # ディーラーは17点以上になるまで引き続ける（本来の動き）
        while calculate_score(self.dealer_hand) < 17:
            await asyncio.sleep(1.5)
            self.dealer_hand.append(get_card())
            await i.edit_original_response(embed=self.create_embed(show=True, status="ディーラーがカードを引いています..."))
        
        p_s = calculate_score(self.player_hand)
        d_s = calculate_score(self.dealer_hand)
        
        # 🛠️ 回収モード（イカサマ）の処理を修正
        if not self.can_win:
            # プレイヤーが21未満、かつ（ディーラーがバーストした、またはプレイヤーの方が強い）場合
            if p_s < 21 and (d_s > 21 or p_s > d_s):
                d_s = p_s + 1  # ディーラーのスコアをプレイヤーより1点高くして勝たせる
                self.dealer_hand = [{"display": "🃏調整", "val": "X", "points": d_s}]
            # プレイヤーがちょうど21の場合は、ディーラーが元々21じゃない限りプレイヤーの勝ちにする（バースト引き分けを防ぐ）

        # 🛠️ 勝敗判定ロジックをシンプルかつ確実なものに変更
        if d_s > 21:
            res = "WIN"   # ディーラーがバーストしたらプレイヤーの勝ち
        elif p_s > d_s:
            res = "WIN"   # プレイヤーの方が高ければ勝ち
        elif p_s < d_s:
            res = "LOSE"  # ディーラーの方が高ければ負け
        else:
            res = "PUSH"  # 同点なら引き分け

        await asyncio.sleep(1.0)
        await self.finish_edit(i, res)

    async def finish_edit(self, i, res):
        self.stop()
        payout = int(self.bet * 2) if res == "WIN" else (int(self.bet) if res == "PUSH" else 0)
        
        if payout > 0:
            self.bot.supabase.rpc('update_user_stats', {'u_id': str(self.user.id), 'coin_change': payout}).execute()
        
        await self.send_log(res, payout)

        color = 0xFFD700 if res == "WIN" else 0xFF0000 if res in ["LOSE", "BUST"] else 0xAAAAAA
        msg = "✨ 勝利！" if res=="WIN" else "💀 敗北..." if res=="LOSE" else "💥 バースト！" if res=="BUST" else "⚖️ 引き分け"
        
        emb = self.create_embed(show=True, status="ゲーム終了")
        emb.color = color
        emb.description = f"## {msg}\n払い戻し: {payout:,}枚"
        
        await i.edit_original_response(embed=emb, view=None)

    async def finish(self, i, res):
        self.stop()
        payout = 0
        await self.send_log(res, payout)
        
        color = 0xFF0000
        msg = "💥 バースト！"
        
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

        jst_now = discord.utils.utcnow() + datetime.timedelta(hours=9)
        time_str = jst_now.strftime('%H:%M')
        
        log_emb = discord.Embed(title="📝 BJ記録", color=0x2b2d31)
        log_emb.description = (
            f"**ユーザー**　**結果**　**損益**\n"
            f"{self.user.mention}　{res}　{profit:+,}枚\n\n"
            f"調整: {adj_status} ・ 今日 {time_str}"
        )
        await chan.send(embed=log_emb)

# --- パネル部分 (永続化) ---
class BJMainView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_bets = {}

    @ui.button(label="金額設定", style=discord.ButtonStyle.secondary, emoji="⌨️", custom_id="bj_set_bet")
    async def set_bet(self, i, b):
        modal = ui.Modal(title="ベット額設定")
        amount_input = ui.TextInput(label="枚数", default="100")
        modal.add_item(amount_input)
        
        async def on_submit(inter):
            if not amount_input.value.isdigit(): 
                return await inter.response.send_message("数字を入れてね", ephemeral=True)
            
            self.user_bets[inter.user.id] = int(amount_input.value)
            await inter.response.send_message(f"✅ {int(amount_input.value):,}枚に設定しました。", ephemeral=True)
            
        modal.on_submit = on_submit
        await i.response.send_modal(modal)

    @ui.button(label="勝負開始！", style=discord.ButtonStyle.danger, emoji="🔥", custom_id="bj_start_game")
    async def start(self, i, b):
        await i.response.defer(ephemeral=True)

        bet = self.user_bets.get(i.user.id, 100)
        
        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
        if not res.data or res.data[0]['coin_count'] < bet:
            return await i.followup.send("❌ コインが足りません", ephemeral=True)
        
        rank_emb = await process_rank_system(self.bot, i.user.id, bet)
        
        gv = BJGameView(self.bot, i.user, bet, rank_emb=rank_emb)
        await gv.check_rigged()
        
        await i.followup.send(embed=gv.create_embed(), view=gv, ephemeral=True)

class BlackjackNewGia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bj", description="ブラックジャックを開始します")
    async def bj(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
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
        await interaction.followup.send(embed=emb, view=BJMainView(self.bot), ephemeral=True)

async def setup(bot):
    await bot.add_cog(BlackjackNewGia(bot))