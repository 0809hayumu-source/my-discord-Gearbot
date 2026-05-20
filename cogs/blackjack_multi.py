import discord
from discord import app_commands, ui
from discord.ext import commands
import random
import asyncio
import datetime

# --- 設定 ---
SUITS = ['♠️', '♥️', '♣️', '♦️']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

# 💴 カジノパネルに設置するボタンの金額設定
PANEL_BUTTONS = [
    {"label": "🪙 100枚でテーブルを開く", "bet": 100, "style": discord.ButtonStyle.primary},
    {"label": "💰 500枚でテーブルを開く", "bet": 500, "style": discord.ButtonStyle.success},
    {"label": "💎 1,000枚でテーブルを開く", "bet": 1000, "style": discord.ButtonStyle.danger},
]

# 📝 結果を保存する専用のログチャンネルID
LOG_CHANNEL_ID = 1505176937491071068

try:
    from cogs.rank import process_rank_system
except ImportError:
    pass

def get_card_value(rank):
    if rank in ['J', 'Q', 'K']: return 10
    if rank == 'A': return 11
    return int(rank)

def calculate_score(hand):
    score = sum(get_card_value(c['rank']) for c in hand)
    aces = sum(1 for c in hand if c['rank'] == 'A')
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score

class BJPlayer:
    def __init__(self, user, bet):
        self.user = user
        self.bet = bet
        self.hand = []
        self.status = "PLAYING" # PLAYING, STAND, BURST

# ==========================================
# 1. 管理者が設置する「カジノパネル」用のUI
# ==========================================
class BJPanelView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # 永続化
        self.bot = bot
        
        for btn in PANEL_BUTTONS:
            button = ui.Button(
                label=btn["label"], 
                style=btn["style"], 
                custom_id=f"bj_panel_spawn_{btn['bet']}"
            )
            button.callback = self.make_callback(btn["bet"])
            self.add_item(button)

    def make_callback(self, bet):
        async def callback(interaction: discord.Interaction):
            user_coins = self.bot.load_data(interaction.user.id)
            if user_coins < bet:
                return await interaction.response.send_message("持ちコインが足りないよ！", ephemeral=True)

            view = MultiBJView(self.bot, interaction.user, bet)
            view.update_buttons()
            
            await interaction.response.send_message(
                content=f"🃏 **{interaction.user.display_name}** が {bet:,}枚 のマルチブラックジャックテーブルを開いたよ！", 
                embed=view.create_embed(), 
                view=view
            )
            view.message = await interaction.original_response()
            
        return callback

# ==========================================
# 2. ゲームが動くテーブル側のUI
# ==========================================
class MultiBJView(ui.View):
    def __init__(self, bot, creator, entry_bet):
        super().__init__(timeout=300)
        self.bot = bot
        self.creator = creator
        self.entry_bet = entry_bet
        self.phase = "WAITING"
        
        self.players = [BJPlayer(creator, entry_bet)]
        self.dealer_hand = []
        
        self.deck = [{"suit": s, "rank": r} for s in SUITS for r in RANKS] * 4
        random.shuffle(self.deck)
        
        self.current_turn_idx = 0
        self.message = None

    def create_embed(self):
        emb = discord.Embed(title="🃏 ギア・マルチブラックジャック", color=0x3498db)
        
        if self.phase == "WAITING":
            emb.description = f"### プレイヤー募集中！\n**参加費**: {self.entry_bet:,} 枚\n現在の参加者: {len(self.players)} / 5人"
        else:
            if self.phase == "ACTION":
                d_cards = f"{self.dealer_hand[0]['suit']}`{self.dealer_hand[0]['rank']}` 🎴"
                d_score = get_card_value(self.dealer_hand[0]['rank'])
            else:
                d_cards = " ".join([f"{c['suit']}`{c['rank']}`" for c in self.dealer_hand])
                d_score = calculate_score(self.dealer_hand)
                
            emb.add_field(name=f"🕵️ ディーラー (計 {d_score})", value=f"### {d_cards}", inline=False)
            emb.add_field(name="━" * 15, value="**プレイヤーたちの状況**", inline=False)
            
            for i, p in enumerate(self.players):
                p_score = calculate_score(p.hand)
                p_cards = " ".join([f"{c['suit']}`{c['rank']}`" for c in p.hand])
                
                status_str = ""
                if p.status == "STAND": status_str = " (スタンド ✋)"
                elif p.status == "BURST": status_str = " (バースト 💥)"
                
                mark = "▶️ " if (i == self.current_turn_idx and self.phase == "ACTION") else "👤 "
                
                emb.add_field(
                    name=f"{mark}{p.user.display_name} [賭け: {p.bet:,}枚]",
                    value=f"手札: {p_cards} (計 **{p_score}**){status_str}",
                    inline=False
                )
        return emb

    def update_buttons(self):
        self.clear_items()
        if self.phase == "WAITING":
            self.add_item(ui.Button(label="参加する", style=discord.ButtonStyle.primary, custom_id="bj_join"))
            self.add_item(ui.Button(label="ゲーム開始", style=discord.ButtonStyle.danger, custom_id="bj_start"))
        elif self.phase == "ACTION":
            self.add_item(ui.Button(label="ヒット (引く)", style=discord.ButtonStyle.success, custom_id="bj_hit"))
            self.add_item(ui.Button(label="スタンド (勝負)", style=discord.ButtonStyle.secondary, custom_id="bj_stand"))

    async def interaction_check(self, i: discord.Interaction) -> bool:
        c_id = i.data["custom_id"]
        
        if self.phase == "WAITING":
            if c_id == "bj_join":
                if any(p.user.id == i.user.id for p in self.players):
                    await i.response.send_message("もう席に座っているよ！", ephemeral=True)
                    return False
                if len(self.players) >= 5:
                    await i.response.send_message("満席（最大5人）だよ！", ephemeral=True)
                    return False
                
                user_coins = self.bot.load_data(i.user.id)
                if user_coins < self.entry_bet:
                    await i.response.send_message("コインが足りないよ！", ephemeral=True)
                    return False
                
                self.players.append(BJPlayer(i.user, self.entry_bet))
                await i.response.edit_message(embed=self.create_embed())
                return True
                
            elif c_id == "bj_start":
                if i.user.id != self.creator.id:
                    await i.response.send_message("ゲームを開始できるのは主催者だけだよ！", ephemeral=True)
                    return False
                
                await i.response.defer()

                for p in self.players:
                    try:
                        await process_rank_system(self.bot, p.user.id, p.bet)
                    except Exception as e:
                        print(f"ランクシステム連動エラー (参加時): {e}")
                        self.bot.add_data(p.user.id, -p.bet)
                
                self.phase = "ACTION"
                self.dealer_hand = [self.deck.pop(), self.deck.pop()]
                for p in self.players:
                    p.hand = [self.deck.pop(), self.deck.pop()]
                
                self.update_buttons()
                await self.message.edit(embed=self.create_embed(), view=self)
                return True

        if self.phase == "ACTION":
            current_player = self.players[self.current_turn_idx]
            if i.user.id != current_player.user.id:
                await i.response.send_message(f"今は {current_player.user.display_name} さんの番だよ！", ephemeral=True)
                return False
            
            if c_id == "bj_hit":
                current_player.hand.append(self.deck.pop())
                if calculate_score(current_player.hand) > 21:
                    current_player.status = "BURST"
                    await self.next_turn(i)
                else:
                    await i.response.edit_message(embed=self.create_embed())
                    
            elif c_id == "bj_stand":
                current_player.status = "STAND"
                await self.next_turn(i)
                
            return True
        return False

    async def next_turn(self, i):
        self.current_turn_idx += 1
        if self.current_turn_idx < len(self.players):
            await i.response.edit_message(embed=self.create_embed(), view=self)
        else:
            self.phase = "LOGIC_END"
            self.clear_items()
            await i.response.edit_message(embed=self.create_embed(), view=None)
            await self.dealer_process()

    async def dealer_process(self):
        if any(p.status != "BURST" for p in self.players):
            while calculate_score(self.dealer_hand) < 17:
                await asyncio.sleep(1.5)
                self.dealer_hand.append(self.deck.pop())
                await self.message.edit(embed=self.create_embed())

        d_score = calculate_score(self.dealer_hand)
        result_embed = self.create_embed()
        result_embed.title = "🏆 ブラックジャック結果発表"
        
        result_text = ""
        for p in self.players:
            p_score = calculate_score(p.hand)
            win_amount = 0
            
            if p.status == "BURST":
                status_msg = "❌ バースト（負け）"
            elif d_score > 21:
                status_msg = "🎉 ディーラーバースト（勝ち！）"
                win_amount = p.bet * 2
            elif p_score > d_score:
                status_msg = "🎉 勝ち！"
                win_amount = p.bet * 2
            elif p_score == d_score:
                status_msg = "🤝 引き分け（コイン返還）"
                win_amount = p.bet
            else:
                status_msg = "❌ 負け"

            if win_amount > 0:
                self.bot.add_data(p.user.id, win_amount)
                result_text += f"**{p.user.display_name}**: {status_msg} ➔ **+{win_amount:,}枚**\n"
            else:
                result_text += f"**{p.user.display_name}**: {status_msg} ➔ **-{p.bet:,}枚**\n"

        result_embed.add_field(name="📊 最終結果", value=result_text, inline=False)
        
        # ⚠️ ユーザーへ向けた「消えちゃうよ」の注意書きメッセージを一番下に差し込む
        result_embed.set_footer(
            text="⏳ このゲーム画面は30秒後に自動で消去されます。\n"
                "見逃した戦績はマルチブラックジャックログ（#マルチブラックジャックログ）でいつでも確認可能です！"
        )
        
        # 1. 修正された最新のEmbedでゲームを一度更新（ボタンは非表示）
        await self.message.edit(embed=result_embed, view=None)

        # 2. ログ用チャンネルへまったく同じ結果Embedを転送
        try:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    content=f"📝 テーブル終了ログ (参加人数: {len(self.players)}人)", 
                    embed=result_embed
                )
        except Exception as e:
            print(f"ログ転送エラー: {e}")

        # 3. 30秒待機してから、元の卓のメッセージを綺麗に削除
        await asyncio.sleep(30)
        try:
            await self.message.delete()
        except discord.NotFound:
            pass # すでにユーザー等によって消されていた場合はスルー

# ==========================================
# 3. スラッシュコマンド（管理者用）
# ==========================================
class BlackjackMulti(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bj_panel", description="【管理者専用】マルチブラックジャックの設置パネルを送信します")
    @app_commands.default_permissions(administrator=True)
    async def bj_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏢 ギア・マルチブラックジャック会場",
            description="下のボタンを押すと、指定した金額のテーブルをその場に開きます！\n最大5人まで同時に同じディーラーと対戦可能です！",
            color=0x2ecc71
        )
        view = BJPanelView(self.bot)
        await interaction.response.send_message("カジノパネルを設置したよ！", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(BlackjackMulti(bot))