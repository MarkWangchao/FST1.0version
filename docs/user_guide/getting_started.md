# Getting Started with the Trading Platform

Welcome to our algorithmic trading platform! This guide will help you get started with the platform, from creating your account to executing your first trade.

## Table of Contents

1. [Creating an Account](#creating-an-account)
2. [Platform Overview](#platform-overview)
3. [Setting Up Your First Strategy](#setting-up-your-first-strategy)
4. [Executing Your First Trade](#executing-your-first-trade)
5. [Monitoring Your Trades](#monitoring-your-trades)
6. [Next Steps](#next-steps)

## Creating an Account

1. Visit our website at [https://tradingplatform.com](https://tradingplatform.com)
2. Click on the "Sign Up" button in the top right corner
3. Fill in your details and follow the verification process
4. Once verified, log in to access the platform

## Platform Overview

After logging in, you'll see the main dashboard:

![Dashboard Overview](../assets/images/dashboard_overview.png)

The dashboard consists of several key areas:

1. **Navigation Menu** - Located on the left side, providing access to all platform features
2. **Market Overview** - Displaying current market data for your tracked symbols
3. **Portfolio Summary** - Showing your current holdings and overall performance
4. **Active Strategies** - Listing your running trading strategies
5. **Recent Activity** - Displaying recent trades and system notifications

### Key Sections

- **Markets**: Browse available markets, view price charts, and market depth
- **Portfolio**: Track your holdings, transaction history, and performance metrics
- **Strategies**: Create, configure, and monitor your trading strategies
- **Backtesting**: Test your strategies against historical data
- **Reports**: Generate detailed reports on your trading performance
- **Settings**: Configure your account, API keys, notifications, and preferences

## Setting Up Your First Strategy

Let's set up a simple moving average crossover strategy:

1. Navigate to "Strategies" in the main menu
2. Click on "Create New Strategy"
3. Select "Moving Average Crossover" from the template list
4. Configure the strategy parameters:
   - **Market**: Select your preferred market (e.g., BTC/USDT)
   - **Short Period**: Enter the period for the fast moving average (e.g., 10)
   - **Long Period**: Enter the period for the slow moving average (e.g., 30)
   - **Position Size**: Define how much to invest (e.g., 10% of your portfolio)
   - **Stop Loss**: Set your stop loss percentage (e.g., 5%)
   - **Take Profit**: Set your take profit percentage (e.g., 10%)
5. Click on "Backtest" to test your strategy against historical data
6. Review the backtest results and adjust parameters if needed
7. When you're satisfied with the results, click "Save Strategy"

## Executing Your First Trade

To execute your first trade using the strategy you've created:

1. Navigate to your saved strategy
2. Click on "Activate"
3. Confirm the activation in the dialog
4. The strategy is now live and will execute trades based on the configured rules

Alternatively, you can execute a manual trade:

1. Navigate to "Markets" and select your preferred market
2. On the trading panel, select:
   - **Buy/Sell**: Choose your trade direction
   - **Amount**: Enter the amount to trade
   - **Price**: Set your limit price or use market price
   - **Order Type**: Choose between Market, Limit, Stop, etc.
3. Review your order details
4. Click "Submit Order" to execute the trade

## Monitoring Your Trades

Once your strategy is active or you've placed manual trades, you can monitor them:

1. **Active Orders**: View your pending orders in the "Orders" section
2. **Positions**: Track your open positions in the "Portfolio" section
3. **Strategy Performance**: Monitor your strategy's performance in the "Strategies" section
4. **Trade History**: View your executed trades in the "History" section

The platform provides real-time updates on your trades and positions, allowing you to track performance and make adjustments as needed.

## Next Steps

Now that you've set up your first strategy and executed your first trade, here are some next steps to explore:

1. **Explore Advanced Strategies**: Try out more complex strategies using our strategy builder
2. **Connect to Multiple Exchanges**: Add API keys for other supported exchanges
3. **Set Up Notifications**: Configure alerts for important events
4. **Optimize Your Strategies**: Use our optimization tools to improve performance
5. **Join Our Community**: Connect with other traders in our forum
6. **Learn More**: Explore our detailed guides on [strategy development](strategies.md) and [platform configuration](configuration.md)

## Getting Help

If you encounter any issues or have questions:

- Check our [FAQ](../faq.md) section
- Refer to the detailed [documentation](../index.md)
- Contact our support team via the "Help" button in the platform
- Join our community forums to ask questions and share experiences

We're here to help you succeed in your trading journey!